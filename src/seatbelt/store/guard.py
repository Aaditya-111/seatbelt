"""GuardStore: payments, reservations, approvals and the audit trail, all transactional.

Key guarantee: judging a payment and reserving its budget happen inside ONE write

transaction, so concurrent requests can never jointly overspend a mandate.

Payment life cycle (any other move raises InvalidTransitionError):

    submit ──► DENIED                                   (terminal)

           ├─► RESERVED ──► CAPTURED                    (terminal)

           │            └─► FAILED / CANCELLED          (budget released)

           └─► PENDING_APPROVAL ──► RESERVED            (human approved)

                                ├─► REJECTED            (human said no)

                                └─► CANCELLED           (mandate revoked/expired)

"""

from __future__ import annotations

import json

import re

import sqlite3

import uuid

from datetime import datetime, timezone

from decimal import Decimal

from typing import Any

from pydantic import SecretStr

from seatbelt.errors import (

    IdempotencyConflictError,

    InvalidTransitionError,

    MandateExpiredError,

    MandateRevokedError,

    NotFoundError,

)

from seatbelt.mandate.models import Mandate

from seatbelt.policy import PaymentRequest, PolicyConfig, Verdict, evaluate

from seatbelt.policy.models import Reason

from seatbelt.store import audit

from seatbelt.store.db import Database

from seatbelt.store.models import (

    HOLDING_STATUSES,
    ChainStatus,
    PaymentChannel,
    PaymentRecord,
    PaymentStatus,
    StoredMandate,

)

_ACTOR = re.compile(r"^[A-Za-z0-9_.:@+-]{1,64}$")

_EXTERNAL_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")

_VERDICT_TO_STATUS = {

    Verdict.ALLOW: PaymentStatus.RESERVED,

    Verdict.REQUIRE_APPROVAL: PaymentStatus.PENDING_APPROVAL,

    Verdict.DENY: PaymentStatus.DENIED,

}

def _now(now: datetime | None) -> datetime:

    return (now or datetime.now(timezone.utc)).astimezone(timezone.utc)

def _actor(value: str) -> str:

    value = value.strip() if isinstance(value, str) else ""

    if not _ACTOR.fullmatch(value):

        raise ValueError("actor must be 1-64 characters of letters, digits, and _ . : @ + -")

    return value

def _external_id(value: str, what: str) -> str:

    if not isinstance(value, str) or not _EXTERNAL_ID.fullmatch(value):

        raise ValueError(f"invalid {what}")

    return value

def _to_record(row: sqlite3.Row) -> PaymentRecord:

    return PaymentRecord(

        payment_id=row["payment_id"],

        mandate_id=row["mandate_id"],

        request_id=row["request_id"],

        agent_id=row["agent_id"],

        payee=row["payee"],

        amount=Decimal(row["amount"]),

        currency=row["currency"],

        description=row["description"],

        status=PaymentStatus(row["status"]),

        verdict=Verdict(row["verdict"]),

        reasons=tuple(Reason.model_validate(r) for r in json.loads(row["reasons"])),

        payment_channel=PaymentChannel(row["payment_channel"]),

        paypal_order_id=row["paypal_order_id"],

        paypal_approve_url=row["paypal_approve_url"],

        paypal_capture_id=row["paypal_capture_id"],

        decided_by=row["decided_by"],

        failure=row["failure"],

        created_at=datetime.fromisoformat(row["created_at"]),

        updated_at=datetime.fromisoformat(row["updated_at"]),

    )

class GuardStore:

    def __init__(

        self,

        db: Database,

        signing_key: SecretStr | str | bytes,

        *,

        policy_config: PolicyConfig | None = None,

    ) -> None:

        self._db = db

        self._audit_key = audit.derive_audit_key(signing_key)

        self._policy_config = policy_config or PolicyConfig()

    # ------------------------------------------------------------------ helpers

    def _log(

        self,

        conn: sqlite3.Connection,

        event: str,

        actor: str,

        subject_id: str,

        data: dict[str, Any],

        now: datetime,

    ) -> None:

        audit.append(

            conn,

            self._audit_key,

            event=event,

            actor=actor,

            subject_id=subject_id,

            data=data,

            now=now,

        )

    @staticmethod

    def _committed(conn: sqlite3.Connection, mandate_id: str) -> Decimal:

        marks = ",".join("?" * len(HOLDING_STATUSES))

        rows = conn.execute(

            f"SELECT amount FROM payments WHERE mandate_id = ? AND status IN ({marks})",

            (mandate_id, *[s.value for s in HOLDING_STATUSES]),

        ).fetchall()

        return sum((Decimal(r["amount"]) for r in rows), Decimal("0"))

    @staticmethod

    def _load_payment(conn: sqlite3.Connection, payment_id: str) -> sqlite3.Row:

        row = conn.execute("SELECT * FROM payments WHERE payment_id = ?", (payment_id,)).fetchone()

        if row is None:

            raise NotFoundError(f"payment {payment_id} not found")

        return row

    @staticmethod

    def _require_status(row: sqlite3.Row, allowed: set[PaymentStatus], action: str) -> None:

        current = PaymentStatus(row["status"])

        if current not in allowed:

            raise InvalidTransitionError(

                f"cannot {action} a payment that is {current.value} "

                f"(allowed from: {', '.join(sorted(s.value for s in allowed))})"

            )
    
    @staticmethod

    def _require_channel(
        row: sqlite3.Row,
        expected: PaymentChannel,
        action: str,
    ) -> None:
       actual = PaymentChannel(row["payment_channel"])
       if actual is not expected:
        raise InvalidTransitionError(
            f"cannot {action} a {actual.value} payment through "
            f"the {expected.value} execution path"
        )
    @staticmethod

    def _update(

        conn: sqlite3.Connection,

        payment_id: str,

        now: datetime,

        *,

        status: PaymentStatus,

        **fields: str | None,

    ) -> sqlite3.Row:

        allowed_cols = {"decided_by", "failure", "paypal_order_id", "paypal_approve_url", "paypal_capture_id"}

        assert set(fields) <= allowed_cols

        sets = ["status = ?", "updated_at = ?", *[f"{c} = ?" for c in fields]]

        conn.execute(

            f"UPDATE payments SET {', '.join(sets)} WHERE payment_id = ?",

            (status.value, now.isoformat(), *fields.values(), payment_id),

        )

        return conn.execute("SELECT * FROM payments WHERE payment_id = ?", (payment_id,)).fetchone()

    # ------------------------------------------------------------------ mandates

    def register_mandate(

        self, mandate: Mandate, token: str, *, actor: str = "system", now: datetime | None = None

    ) -> None:

        """Record a (signature-verified) mandate. Registering the same one twice is a no-op."""

        now = _now(now)

        actor = _actor(actor)

        with self._db.transaction() as conn:

            cur = conn.execute(

                "INSERT OR IGNORE INTO mandates (mandate_id, agent_id, currency, token, "

                "mandate_json, expires_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",

                (

                    mandate.mandate_id,

                    mandate.agent_id,

                    mandate.currency,

                    token,

                    mandate.model_dump_json(),

                    mandate.expires_at.isoformat(),

                    now.isoformat(),

                ),

            )

            if cur.rowcount:

                self._log(

                    conn,

                    "mandate.registered",

                    actor,

                    mandate.mandate_id,

                    {

                        "agent_id": mandate.agent_id,

                        "currency": mandate.currency,

                        "total_limit": str(mandate.total_limit),

                        "per_payment_limit": str(mandate.per_payment_limit),

                        "approval_threshold": str(mandate.approval_threshold),

                        "allowed_payees": list(mandate.allowed_payees),

                        "expires_at": mandate.expires_at.isoformat(),

                    },

                    now,

                )

    def get_mandate(self, mandate_id: str) -> StoredMandate:

        with self._db.transaction(write=False) as conn:

            row = conn.execute(

                "SELECT * FROM mandates WHERE mandate_id = ?", (mandate_id,)

            ).fetchone()

            if row is None:

                raise NotFoundError(f"mandate {mandate_id} not found")

            return StoredMandate(

                mandate=Mandate.model_validate_json(row["mandate_json"]),

                committed=self._committed(conn, mandate_id),

                created_at=datetime.fromisoformat(row["created_at"]),

                revoked_at=datetime.fromisoformat(row["revoked_at"]) if row["revoked_at"] else None,

            )

    def revoke_mandate(self, mandate_id: str, actor: str, *, now: datetime | None = None) -> int:

        """Kill switch. Cancels every unfinished payment; captured money stays captured.

        Returns how many payments were cancelled. Revoking twice is harmless.

        """

        now = _now(now)

        actor = _actor(actor)

        with self._db.transaction() as conn:

            row = conn.execute(

                "SELECT revoked_at FROM mandates WHERE mandate_id = ?", (mandate_id,)

            ).fetchone()

            if row is None:

                raise NotFoundError(f"mandate {mandate_id} not found")

            if row["revoked_at"]:

                return 0

            conn.execute(

                "UPDATE mandates SET revoked_at = ? WHERE mandate_id = ?",

                (now.isoformat(), mandate_id),

            )

            open_rows = conn.execute(

                "SELECT payment_id FROM payments WHERE mandate_id = ? AND status IN (?, ?, ?)",

                (mandate_id, PaymentStatus.PENDING_APPROVAL.value, PaymentStatus.RESERVED.value, PaymentStatus.AWAITING_PAYER.value,),

            ).fetchall()

            for r in open_rows:

                self._update(

                    conn,

                    r["payment_id"],

                    now,

                    status=PaymentStatus.CANCELLED,

                    failure="mandate revoked",

                )

                self._log(

                    conn,

                    "payment.cancelled",

                    actor,

                    r["payment_id"],

                    {"reason": "mandate revoked"},

                    now,

                )

            self._log(

                conn,

                "mandate.revoked",

                actor,

                mandate_id,

                {"payments_cancelled": len(open_rows)},

                now,

            )

            return len(open_rows)

    # ------------------------------------------------------------------ payments

    def submit_payment(

        self, mandate: Mandate, request: PaymentRequest, *, payment_channel: PaymentChannel | str = PaymentChannel.EXECUTOR, now: datetime | None = None,

    ) -> PaymentRecord:

        """Judge a payment and, unless denied, reserve its budget atomically.

        Re-sending the same request_id returns the original record instead of a duplicate.

        """

        now = _now(now)

        try:
            payment_channel = PaymentChannel(payment_channel)
        except ValueError:
            raise ValueError("unsupported payment channel") from None

        with self._db.transaction() as conn:

            mrow = conn.execute(

                "SELECT revoked_at FROM mandates WHERE mandate_id = ?", (mandate.mandate_id,)

            ).fetchone()

            if mrow is None:

                raise NotFoundError(f"mandate {mandate.mandate_id} is not registered")

            if mrow["revoked_at"]:

                raise MandateRevokedError("this mandate has been revoked")

            existing = conn.execute(

                "SELECT * FROM payments WHERE mandate_id = ? AND request_id = ?",

                (mandate.mandate_id, request.request_id),

            ).fetchone()

            if existing is not None:

                same = (

                    existing["agent_id"] == request.agent_id

                    and existing["payee"] == request.payee

                    and Decimal(existing["amount"]) == request.charge_amount

                    and existing["currency"] == request.money.currency

                    and PaymentChannel(existing["payment_channel"])
                     
                    is payment_channel

                )

                if not same:

                    raise IdempotencyConflictError(

                        f"request_id '{request.request_id}' was already used with different details"

                    )

                return _to_record(existing)

            committed = self._committed(conn, mandate.mandate_id)

            decision = evaluate(

                mandate, request, committed=committed, now=now, config=self._policy_config

            )

            status = _VERDICT_TO_STATUS[decision.verdict]

            payment_id = uuid.uuid4().hex

            conn.execute(

                "INSERT INTO payments (payment_id, mandate_id, request_id, agent_id, payee, "

                "amount, currency, description, status, verdict, reasons, payment_channel, "
                "created_at, updated_at) "

                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",

                (

                    payment_id,

                    mandate.mandate_id,

                    request.request_id,

                    request.agent_id,

                    request.payee,

                    str(decision.amount),

                    decision.currency,

                    request.description,

                    status.value,

                    decision.verdict.value,

                    json.dumps([r.model_dump(mode="json") for r in decision.reasons]),

                                        payment_channel.value,

                    now.isoformat(),

                    now.isoformat(),

                ),

            )

            self._log(

                conn,

                "payment.submitted",

                request.agent_id,

                payment_id,

                {

                    "mandate_id": mandate.mandate_id,

                    "request_id": request.request_id,

                    "payee": request.payee,

                    "amount": str(decision.amount),

                    "currency": decision.currency,

                    "description": request.description,

                    "verdict": decision.verdict.value,

                    "status": status.value,

                    "reason_codes": [r.code.value for r in decision.reasons],

                    "risk_signals": [s.model_dump(mode="json") for s in request.risk_signals],

                    "committed_before": str(committed),

                },

                now,

            )

            return _to_record(self._load_payment(conn, payment_id))

    def approve_payment(

        self, payment_id: str, approver: str, *,  expected_channel: PaymentChannel = PaymentChannel.EXECUTOR, now: datetime | None = None

    ) -> PaymentRecord:

        """A human approves a held payment. If its mandate has expired meanwhile, it is

        cancelled (budget released) and MandateExpiredError is raised."""

        now = _now(now)

        approver = _actor(approver)

        failure: Exception | None = None

        with self._db.transaction() as conn:

            row = self._load_payment(conn, payment_id)

            self._require_channel(row, expected_channel, "approve")

            self._require_status(row, {PaymentStatus.PENDING_APPROVAL}, "approve")

            mrow = conn.execute(

                "SELECT mandate_json, revoked_at FROM mandates WHERE mandate_id = ?",

                (row["mandate_id"],),

            ).fetchone()

            mandate = Mandate.model_validate_json(mrow["mandate_json"])

            if mrow["revoked_at"]:

                failure = MandateRevokedError("this mandate has been revoked")

            elif now >= mandate.expires_at:

                failure = MandateExpiredError("the mandate expired before approval")

            if failure is not None:

                updated = self._update(

                    conn, payment_id, now, status=PaymentStatus.CANCELLED, failure=str(failure)

                )

                self._log(

                    conn, "payment.cancelled", approver, payment_id, {"reason": str(failure)}, now

                )

            else:

                updated = self._update(

                    conn, payment_id, now, status=PaymentStatus.RESERVED, decided_by=approver

                )

                self._log(conn, "payment.approved", approver, payment_id, {}, now)

            record = _to_record(updated)

        if failure is not None:

            raise failure

        return record

    def reject_payment(

        self, payment_id: str, approver: str, reason: str = "", *, now: datetime | None = None

    ) -> PaymentRecord:

        now = _now(now)

        approver = _actor(approver)

        with self._db.transaction() as conn:

            row = self._load_payment(conn, payment_id)

            self._require_status(row, {PaymentStatus.PENDING_APPROVAL}, "reject")

            updated = self._update(

                conn,

                payment_id,

                now,

                status=PaymentStatus.REJECTED,

                decided_by=approver,

                failure=reason[:300] or None,

            )

            self._log(conn, "payment.rejected", approver, payment_id, {"reason": reason[:300]}, now)

            return _to_record(updated)

    def attach_order(

        self, payment_id: str, order_id: str, *,  now: datetime | None = None

    ) -> PaymentRecord:

        now = _now(now)

        order_id = _external_id(order_id, "PayPal order id")

        with self._db.transaction() as conn:

            row = self._load_payment(conn, payment_id)

            self._require_status(row, {PaymentStatus.RESERVED}, "attach an order to")

            updated = self._update(

                conn, payment_id, now, status=PaymentStatus.RESERVED, paypal_order_id=order_id

            )

            self._log(

                conn, "payment.order_created", "system", payment_id, {"order_id": order_id}, now

            )

            return _to_record(updated)

    def attach_checkout(

        self,

        payment_id: str,

        order_id: str,

        approve_url: str,

        *,

        now: datetime | None = None,

    ) -> PaymentRecord:

        now = _now(now)

        order_id = _external_id(order_id, "PayPal order id")

        if not isinstance(approve_url, str):

            raise ValueError("invalid PayPal approval URL")

        approve_url = approve_url.strip()

        from urllib.parse import urlsplit

        parsed = urlsplit(approve_url)

        if (

            parsed.scheme != "https"

            or parsed.hostname not in {

                "www.sandbox.paypal.com",

                "www.paypal.com",

            }

            or not parsed.path.startswith("/checkoutnow")

            or parsed.username is not None

            or parsed.password is not None

        ):

            raise ValueError("invalid PayPal approval URL")

        with self._db.transaction() as conn:

            row = self._load_payment(conn, payment_id)

            self._require_status(row, {PaymentStatus.RESERVED}, "attach a checkout to")

            updated = self._update(

                conn,

                payment_id,

                now,

                status=PaymentStatus.AWAITING_PAYER,

                paypal_order_id=order_id,

                paypal_approve_url=approve_url,

            )

            self._log(

                conn,

                "payment.checkout_created",

                "system",

                payment_id,

                {

                    "order_id": order_id,

                    "status": PaymentStatus.AWAITING_PAYER.value,

                },

                now,

            )

            return _to_record(updated)

    def mark_payer_approved(
        self,
        payment_id: str,
        *,
        now: datetime | None = None,
    ) -> PaymentRecord:
        """Record verified PayPal payer approval.

        The caller must verify the PayPal order with PayPal's API before calling
        this method. A browser redirect alone is not proof of payer approval.
        """
        now = _now(now)
        failure: Exception | None = None

        with self._db.transaction() as conn:
            row = self._load_payment(conn, payment_id)
            self._require_status(
                row,
                {PaymentStatus.AWAITING_PAYER},
                "mark payer approval for",
            )

            mrow = conn.execute(
                "SELECT mandate_json, revoked_at FROM mandates WHERE mandate_id = ?",
                (row["mandate_id"],),
            ).fetchone()
            mandate = Mandate.model_validate_json(mrow["mandate_json"])

            if mrow["revoked_at"]:
                failure = MandateRevokedError("this mandate has been revoked")
            elif now >= mandate.expires_at:
                failure = MandateExpiredError(
                    "the mandate expired before payer approval"
                )

            if failure is not None:
                updated = self._update(
                    conn,
                    payment_id,
                    now,
                    status=PaymentStatus.CANCELLED,
                    failure=str(failure),
                )
                self._log(
                    conn,
                    "payment.cancelled",
                    "system",
                    payment_id,
                    {"reason": str(failure)},
                    now,
                )
            else:
                updated = self._update(
                    conn,
                    payment_id,
                    now,
                    status=PaymentStatus.RESERVED,
                )
                self._log(
                    conn,
                    "payment.payer_approved",
                    "system",
                    payment_id,
                    {"order_id": row["paypal_order_id"]},
                    now,
                )

            record = _to_record(updated)

        if failure is not None:
            raise failure

        return record

    def record_paypal_cancel_requested(
        self,
        payment_id: str,
        *,
        now: datetime | None = None,
    ) -> PaymentRecord:
        """Record a browser cancellation request without releasing its reservation."""
        now = _now(now)

        with self._db.transaction() as conn:
            row = self._load_payment(conn, payment_id)
            self._require_channel(row, PaymentChannel.PAYPAL, "cancel")

            if row["status"] == PaymentStatus.CANCELLED.value:
                return _to_record(row)

            self._require_status(
                row,
                {PaymentStatus.AWAITING_PAYER},
                "request cancellation for",
            )

            existing = conn.execute(
                """
                SELECT 1
                FROM audit_log
                WHERE event = ?
                  AND subject_id = ?
                LIMIT 1
                """,
                ("payment.paypal_cancel_requested", payment_id),
            ).fetchone()

            if existing is None:
                self._log(
                    conn,
                    "payment.paypal_cancel_requested",
                    "system",
                    payment_id,
                    {"order_id": row["paypal_order_id"]},
                    now,
                )

            return _to_record(row)

    def mark_paypal_cancelled(
        self,
        payment_id: str,
        *,
        now: datetime | None = None,
    ) -> PaymentRecord:
        """Cancel an unapproved PayPal checkout and release its reservation."""
        now = _now(now)

        with self._db.transaction() as conn:
            row = self._load_payment(conn, payment_id)
            self._require_channel(row, PaymentChannel.PAYPAL, "cancel")
            self._require_status(
                row,
                {PaymentStatus.AWAITING_PAYER},
                "cancel PayPal checkout for",
            )

            updated = self._update(
                conn,
                payment_id,
                now,
                status=PaymentStatus.CANCELLED,
                failure="PayPal checkout cancelled by payer",
            )
            self._log(
                conn,
                "payment.paypal_cancelled",
                "system",
                payment_id,
                {"order_id": row["paypal_order_id"]},
                now,
            )
            return _to_record(updated)

    def mark_captured(
        self,
        payment_id: str,
        capture_id: str,
        *,
        now: datetime | None = None,
    ) -> PaymentRecord:
      now = _now(now)
      capture_id = _external_id(capture_id, "PayPal capture id")

      with self._db.transaction() as conn:
          row = self._load_payment(conn, payment_id)

            # A second service instance may receive the same successful
            # PayPal capture after the first instance has committed it.
            # Accept only the exact same PayPal capture ID.
          if PaymentStatus(row["status"]) is PaymentStatus.CAPTURED:
            self._require_channel(
                row,
                PaymentChannel.PAYPAL,
                "confirm capture for",
            )
            if row["paypal_capture_id"] == capture_id:
                    return _to_record(row)

          self._require_status(
            row,
            {PaymentStatus.RESERVED},
            "capture",
          )

          updated = self._update(
                conn,
                payment_id,
                now,
                status=PaymentStatus.CAPTURED,
                paypal_capture_id=capture_id,
           )

          self._log(
                conn,
                "payment.captured",
                "system",
                payment_id,
                {"capture_id": capture_id},
                now,
        )

      return _to_record(updated)

    def mark_failed(

        self, payment_id: str, failure: str, *, now: datetime | None = None

    ) -> PaymentRecord:

        """The PayPal step failed. Releases the reservation."""

        now = _now(now)

        with self._db.transaction() as conn:

            row = self._load_payment(conn, payment_id)

            self._require_status(row, {PaymentStatus.RESERVED}, "fail")

            updated = self._update(

                conn, payment_id, now, status=PaymentStatus.FAILED, failure=failure[:300]

            )

            self._log(conn, "payment.failed", "system", payment_id, {"failure": failure[:300]}, now)

            return _to_record(updated)

    # ------------------------------------------------------------------ queries

    def get_payment(self, payment_id: str) -> PaymentRecord:

        with self._db.transaction(write=False) as conn:

            return _to_record(self._load_payment(conn, payment_id))

    def get_payment_by_order_id(self, order_id: str) -> PaymentRecord:
        """Resolve a PayPal callback using an order ID stored by Seatbelt."""
        with self._db.transaction(write=False) as conn:
            row = conn.execute(
                "SELECT * FROM payments WHERE paypal_order_id = ?",
                (order_id,),
            ).fetchone()
            if row is None:
                raise NotFoundError("PayPal order not found")
            return _to_record(row)

    def list_payments(

        self,

        *,

        mandate_id: str | None = None,

        status: PaymentStatus | None = None,

        limit: int = 100,

        offset: int = 0,

    ) -> list[PaymentRecord]:

        clauses, params = [], []

        if mandate_id is not None:

            clauses.append("mandate_id = ?")

            params.append(mandate_id)

        if status is not None:

            clauses.append("status = ?")

            params.append(status.value)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        limit = max(1, min(int(limit), 500))

        with self._db.transaction(write=False) as conn:

            rows = conn.execute(

                f"SELECT * FROM payments {where} "

                "ORDER BY created_at DESC, rowid DESC LIMIT ? OFFSET ?",

                (*params, limit, max(0, int(offset))),

            ).fetchall()

            return [_to_record(r) for r in rows]

    def list_audit(self, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:

        limit = max(1, min(int(limit), 500))

        with self._db.transaction(write=False) as conn:

            rows = conn.execute(

                "SELECT * FROM audit_log ORDER BY seq DESC LIMIT ? OFFSET ?",

                (limit, max(0, int(offset))),

            ).fetchall()

        return [

            {

                "seq": r["seq"],

                "ts": r["ts"],

                "event": r["event"],

                "actor": r["actor"],

                "subject_id": r["subject_id"],

                "data": json.loads(r["data"]),

                "hash": r["hash"],

            }

            for r in rows

        ]

    def verify_audit(self) -> ChainStatus:

        with self._db.transaction(write=False) as conn:

            return audit.verify(conn, self._audit_key)
