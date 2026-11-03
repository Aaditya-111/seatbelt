"""GuardService: the use-cases of the guard, independent of HTTP.

  agent  : submit a payment (authenticated by its signed mandate token)
  admin  : issue / revoke mandates, approve / reject / retry payments

It joins the store (decisions, reservations, audit) to an executor (moving money).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from pydantic import SecretStr

from seatbelt.errors import (
    ExecutionError,
    MandateRevokedError,
    MandateSignatureError,
    NotFoundError,
)
from seatbelt.mandate import Mandate, decode_mandate, issue_mandate
from seatbelt.paypal.models import Money
from seatbelt.policy import PaymentRequest
from seatbelt.service.executor import PaymentExecutor
from seatbelt.store import ChainStatus, GuardStore, PaymentRecord, PaymentStatus, StoredMandate

log = logging.getLogger(__name__)

_LOCK_STRIPES = 64


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class GuardService:
    def __init__(
        self,
        store: GuardStore,
        executor: PaymentExecutor,
        signing_key: SecretStr | str | bytes,
        *,
        max_mandate_ttl: timedelta,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._store = store
        self._executor = executor
        self._key = signing_key
        self._max_ttl = max_mandate_ttl
        self._clock = clock
        # A fixed set of locks, picked by payment id, so one payment is never executed by
        # two threads at once, without growing a lock per payment forever.
        self._locks = [threading.Lock() for _ in range(_LOCK_STRIPES)]

    # ------------------------------------------------------------------ mandates
    def issue_mandate(
        self,
        *,
        agent_id: str,
        currency: str,
        per_payment_limit: str,
        total_limit: str,
        approval_threshold: str,
        allowed_payees: list[str],
        ttl: timedelta,
        actor: str = "admin",
    ) -> tuple[Mandate, str]:
        now = self._clock()
        mandate, token = issue_mandate(
            key=self._key,
            agent_id=agent_id,
            currency=currency,
            per_payment_limit=per_payment_limit,
            total_limit=total_limit,
            approval_threshold=approval_threshold,
            allowed_payees=allowed_payees,
            ttl=ttl,
            max_ttl=self._max_ttl,
            now=now,
        )
        self._store.register_mandate(mandate, token, actor=actor, now=now)
        return mandate, token

    def authenticate_agent(self, token: str) -> Mandate:
        """Verify signature + validity window, and that the mandate is ours and not revoked."""
        mandate = decode_mandate(token, self._key, now=self._clock())
        try:
            stored = self._store.get_mandate(mandate.mandate_id)
        except NotFoundError:
            raise MandateSignatureError("mandate is not recognised") from None
        if stored.revoked_at is not None:
            raise MandateRevokedError("this mandate has been revoked")
        return mandate

    def get_mandate(self, mandate_id: str) -> StoredMandate:
        return self._store.get_mandate(mandate_id)

    def revoke_mandate(self, mandate_id: str, actor: str) -> int:
        return self._store.revoke_mandate(mandate_id, actor, now=self._clock())

    # ------------------------------------------------------------------ payments
    def submit_payment(
        self,
        token: str,
        *,
        request_id: str,
        payee: str,
        amount: str,
        currency: str,
        description: str = "",
    ) -> PaymentRecord:
        """An agent asks to pay. The agent's identity comes from its mandate, never from
        the request body."""
        mandate = self.authenticate_agent(token)
        request = PaymentRequest(
            request_id=request_id,
            agent_id=mandate.agent_id,
            payee=payee,
            money=Money(amount=Decimal(amount), currency=currency),
            description=description,
        )
        record = self._store.submit_payment(mandate, request, now=self._clock())
        return self._execute_if_reserved(record)

    def approve_payment(self, payment_id: str, approver: str) -> PaymentRecord:
        record = self._store.approve_payment(payment_id, approver, now=self._clock())
        return self._execute_if_reserved(record)

    def reject_payment(self, payment_id: str, approver: str, reason: str = "") -> PaymentRecord:
        return self._store.reject_payment(payment_id, approver, reason, now=self._clock())

    def retry_payment(self, payment_id: str) -> PaymentRecord:
        """Re-run a payment stuck in RESERVED (e.g. the server stopped mid-way). Safe: the
        executor is idempotent per payment id and this method re-checks state under a lock."""
        return self._execute_if_reserved(self._store.get_payment(payment_id))

    def get_payment(self, payment_id: str) -> PaymentRecord:
        return self._store.get_payment(payment_id)

    def list_payments(
        self,
        *,
        mandate_id: str | None = None,
        status: PaymentStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[PaymentRecord]:
        return self._store.list_payments(
            mandate_id=mandate_id, status=status, limit=limit, offset=offset
        )

    # ------------------------------------------------------------------ audit
    def list_audit(self, *, limit: int = 100, offset: int = 0) -> list[dict]:
        return self._store.list_audit(limit=limit, offset=offset)

    def verify_audit(self) -> ChainStatus:
        return self._store.verify_audit()

    # ------------------------------------------------------------------ internals
    def _execute_if_reserved(self, record: PaymentRecord) -> PaymentRecord:
        if record.status is not PaymentStatus.RESERVED:
            return record
        lock = self._locks[hash(record.payment_id) % _LOCK_STRIPES]
        with lock:
            # Re-read under the lock: another thread may have finished this payment already.
            current = self._store.get_payment(record.payment_id)
            if current.status is not PaymentStatus.RESERVED:
                return current
            try:
                result = self._executor.execute(current)
            except ExecutionError as exc:
                log.warning("payment %s failed: %s", current.payment_id, exc)
                return self._store.mark_failed(current.payment_id, str(exc), now=self._clock())
            except Exception:
                # Outcome unknown: leave it RESERVED (budget stays held) so an operator can
                # retry safely, and let the caller see a generic server error.
                log.exception("payment %s: executor crashed", current.payment_id)
                raise
            if result.order_id:
                self._store.attach_order(current.payment_id, result.order_id, now=self._clock())
            return self._store.mark_captured(
                current.payment_id, result.capture_id, now=self._clock()
            )