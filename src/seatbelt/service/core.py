"""GuardService: the use-cases of the guard, independent of HTTP.

  agent  : submit a payment (authenticated by its signed mandate token)
  admin  : issue / revoke mandates, approve / reject / retry payments

It joins the store (decisions, reservations, audit) to an executor (moving money).
"""

from __future__ import annotations

import hashlib
import logging
import threading
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from pydantic import SecretStr

from seatbelt.errors import (
    ExecutionError,
    InvalidTransitionError,
    MandateRevokedError,
    MandateSignatureError,
    NotFoundError,
)
from seatbelt.mandate import Mandate, decode_mandate, issue_mandate
from seatbelt.paypal.client import PayPalClient
from seatbelt.paypal.models import Money
from seatbelt.policy import PaymentRequest
from seatbelt.service.executor import PaymentExecutor
from seatbelt.store import ChainStatus, GuardStore, PaymentChannel, PaymentRecord, PaymentStatus, StoredMandate

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
        paypal_client: PayPalClient | None = None,
        paypal_expected_merchant_id: str | None = None,
    ) -> None:
        self._store = store
        self._executor = executor
        self._paypal = paypal_client
        self._paypal_merchant_id = paypal_expected_merchant_id
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
        payment_channel: PaymentChannel = PaymentChannel.EXECUTOR,
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
        record = self._store.submit_payment(
            mandate,
            request,
            payment_channel=payment_channel,
            now=self._clock(),
        )
        return self._execute_if_reserved(record)

    def submit_paypal_payment(
        self,
        token: str,
        *,
        request_id: str,
        payee: str,
        amount: str,
        currency: str,
        description: str = "",
    ) -> PaymentRecord:
        """Submit through the server-selected PayPal channel."""
        if self._paypal is None or not self._paypal_merchant_id:
            raise RuntimeError("PayPal checkout is not fully configured")

        return self.submit_payment(
            token,
            request_id=request_id,
            payee=payee,
            amount=amount,
            currency=currency,
            description=description,
            payment_channel=PaymentChannel.PAYPAL,
        )

    def handle_paypal_webhook(
        self,
        headers: dict[str, str],
        event: dict[str, object],
        raw_event_body: bytes,
    ) -> dict[str, object]:
        """Verify and reconcile PayPal capture webhooks without initiating captures."""
        if self._paypal is None or not self._paypal_merchant_id:
            raise RuntimeError("PayPal checkout is not fully configured")

        if not self._paypal.verify_webhook_signature(headers, event, raw_event_body):
            raise PermissionError("PayPal webhook signature verification failed")

        event_id = event.get("id")
        event_type = event.get("event_type")
        if (
            not isinstance(event_id, str)
            or not event_id
            or len(event_id) > 128
            or not isinstance(event_type, str)
            or not event_type
            or len(event_type) > 128
        ):
            raise ValueError("PayPal webhook event identity is invalid")

        if event_type != "PAYMENT.CAPTURE.COMPLETED":
            return {
                "received": True,
                "processed": False,
                "duplicate": False,
                "reason": "unsupported_event_type",
            }

        resource = event.get("resource")
        if not isinstance(resource, dict):
            raise ValueError("PayPal capture webhook resource is invalid")

        capture_id = resource.get("id")
        capture_status = resource.get("status")
        amount_data = resource.get("amount")
        supplementary = resource.get("supplementary_data")
        related_ids = (
            supplementary.get("related_ids")
            if isinstance(supplementary, dict)
            else None
        )
        order_id = (
            related_ids.get("order_id")
            if isinstance(related_ids, dict)
            else None
        )

        if (
            not isinstance(capture_id, str)
            or not capture_id
            or len(capture_id) > 128
            or capture_status != "COMPLETED"
            or not isinstance(order_id, str)
            or not order_id
            or len(order_id) > 128
            or not isinstance(amount_data, dict)
            or not isinstance(amount_data.get("value"), str)
            or not isinstance(amount_data.get("currency_code"), str)
        ):
            raise ValueError("PayPal capture webhook is missing required fields")

        try:
            event_amount = Decimal(amount_data["value"])
        except Exception as exc:
            raise ValueError("PayPal capture amount is invalid") from exc

        if not event_amount.is_finite() or event_amount <= 0:
            raise ValueError("PayPal capture amount is invalid")

        record = self._store.get_payment_by_order_id(order_id)
        if record.payment_channel is not PaymentChannel.PAYPAL:
            raise NotFoundError("PayPal order not found")

        expected_money = Money(amount=record.amount, currency=record.currency)
        order = self._paypal.get_order(order_id)
        order.verify_for_capture(
            expected_order_id=order_id,
            expected_reference_id=record.payment_id,
            expected_money=expected_money,
            expected_merchant_id=self._paypal_merchant_id,
        )

        if order.status != "COMPLETED" or len(order.purchase_units) != 1:
            raise ValueError("PayPal has not confirmed a completed capture")

        unit = order.purchase_units[0]
        expected_amount = Decimal(expected_money.to_paypal_value())

        if (
            unit.capture_id != capture_id
            or unit.capture_amount != expected_amount
            or unit.capture_currency != expected_money.currency
            or event_amount != expected_amount
            or amount_data["currency_code"] != expected_money.currency
        ):
            raise ValueError("PayPal webhook capture does not match the verified order")

        reconciled, duplicate = self._store.reconcile_paypal_webhook(
            event_id=event_id,
            event_type=event_type,
            payment_id=record.payment_id,
            capture_id=capture_id,
            now=self._clock(),
        )

        return {
            "received": True,
            "processed": True,
            "duplicate": duplicate,
            "payment_id": reconciled.payment_id,
            "status": reconciled.status.value,
        }

    def process_paypal_return(self, order_id: str) -> PaymentRecord:
        """Verify a PayPal browser return against PayPal's Orders API."""
        record = self._store.get_payment_by_order_id(order_id)

        if record.payment_channel is not PaymentChannel.PAYPAL:
            raise NotFoundError("PayPal order not found")

        if self._paypal is None or not self._paypal_merchant_id:
            raise RuntimeError("PayPal checkout is not fully configured")

        if record.status is PaymentStatus.CAPTURED:
            return record

        if record.status not in {
            PaymentStatus.AWAITING_PAYER,
            PaymentStatus.RESERVED,
        }:
            raise InvalidTransitionError(
                "payment is not awaiting PayPal completion"
            )

        return self._complete_paypal_payment(record.payment_id, order_id)

    def process_paypal_cancel(self, order_id: str) -> PaymentRecord:
        """Handle a PayPal cancel callback without assuming it voided the order."""
        record = self._store.get_payment_by_order_id(order_id)

        if record.payment_channel is not PaymentChannel.PAYPAL:
            raise NotFoundError("PayPal order not found")

        if record.status is PaymentStatus.CANCELLED:
            return record

        if self._paypal is None or not self._paypal_merchant_id:
            raise RuntimeError("PayPal checkout is not fully configured")

        lock = self._locks[hash(record.payment_id) % _LOCK_STRIPES]

        with lock:
            current = self._store.get_payment(record.payment_id)

            if current.status is PaymentStatus.CANCELLED:
                return current

            if current.paypal_order_id != order_id:
                raise NotFoundError("PayPal order not found")

            if current.status is not PaymentStatus.AWAITING_PAYER:
                raise InvalidTransitionError(
                    "only an unapproved PayPal checkout can receive a cancel callback"
                )

            order = self._paypal.get_order(order_id)

            expected = {
                "expected_order_id": order_id,
                "expected_reference_id": current.payment_id,
                "expected_money": Money(
                    amount=current.amount,
                    currency=current.currency,
                ),
                "expected_merchant_id": self._paypal_merchant_id,
            }

            # Verify order identity and payment details before trusting the callback.
            order.verify_checkout_identity(**expected)

            if order.status in {"APPROVED", "COMPLETED"}:
                raise ValueError(
                    "PayPal order is not in a cancellable state"
                )

            # Release the reservation only when PayPal independently reports VOIDED.
            if order.status == "VOIDED":
                return self._store.mark_paypal_cancelled(
                    current.payment_id,
                    now=self._clock(),
                )

            # A browser redirect is not proof that the PayPal order is cancelled.
            return self._store.record_paypal_cancel_requested(
                current.payment_id,
                now=self._clock(),
            )

    def approve_payment(self, payment_id: str, approver: str) -> PaymentRecord:
        existing = self._store.get_payment(payment_id)
        record = self._store.approve_payment(
            payment_id,
            approver,
            expected_channel=existing.payment_channel,
            now=self._clock(),
        )
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

    def create_audit_checkpoint(self):
        return self._store.create_audit_checkpoint()

    # ------------------------------------------------------------------ internals
    @staticmethod
    def _paypal_request_id(operation: str, payment_id: str) -> str:
        """Stable PayPal idempotency key for one operation on one payment."""
        raw = f"seatbelt:paypal:{operation}:{payment_id}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:32]

    def _create_paypal_checkout(self, payment: PaymentRecord) -> PaymentRecord:
        self._store.assert_audit_healthy()
        if self._paypal is None or not self._paypal_merchant_id:
            raise RuntimeError("PayPal checkout is not fully configured")


        order = self._paypal.create_order(
            Money(amount=payment.amount, currency=payment.currency),
            description=payment.description,
            reference_id=payment.payment_id,
            request_id=self._paypal_request_id("create", payment.payment_id),
        )

        if not order.approve_url:
            # The remote order may exist. Keep the reservation for safe retry.
            raise RuntimeError("PayPal did not return an approval URL")

        return self._store.attach_checkout(
            payment.payment_id,
            order.id,
            order.approve_url,
            now=self._clock(),
        )

    def _complete_paypal_payment(
        self, payment_id: str, order_id: str
    ) -> PaymentRecord:
        if self._paypal is None or not self._paypal_merchant_id:
            raise RuntimeError("PayPal checkout is not fully configured")

        lock = self._locks[hash(payment_id) % _LOCK_STRIPES]

        with lock:
            current = self._store.get_payment(payment_id)

            if current.status is PaymentStatus.CAPTURED:
                return current

            if current.paypal_order_id != order_id:
                raise NotFoundError("PayPal order not found")

            if current.status not in {
                PaymentStatus.AWAITING_PAYER,
                PaymentStatus.RESERVED,
            }:
                raise InvalidTransitionError(
                    "payment is not awaiting PayPal completion"
                )

            order = self._paypal.get_order(order_id)
            money = Money(amount=current.amount, currency=current.currency)

            order.verify_for_capture(
                expected_order_id=order_id,
                expected_reference_id=current.payment_id,
                expected_money=money,
                expected_merchant_id=self._paypal_merchant_id,
            )

            if current.status is PaymentStatus.AWAITING_PAYER:
                current = self._store.mark_payer_approved(
                    payment_id,
                    now=self._clock(),
                )

            expected_amount = Decimal(money.to_paypal_value())

            # A previous capture may have succeeded even if our HTTP response
            # was lost. Reconcile the completed order instead of capturing again.
            if order.status == "COMPLETED":
                unit = order.purchase_units[0]

                if (
                    not unit.capture_id
                    or unit.capture_amount != expected_amount
                    or unit.capture_currency != money.currency
                ):
                    raise RuntimeError(
                        "Completed PayPal order has no matching capture; "
                        "manual reconciliation is required"
                    )

                return self._store.mark_captured(
                    payment_id,
                    unit.capture_id,
                    now=self._clock(),
                )
            self._store.assert_audit_healthy()
            result = self._paypal.capture_order(
                order_id,
                request_id=self._paypal_request_id("capture", payment_id),
            )

            if (
                result.order_id != order_id
                or result.status != "COMPLETED"
                or result.amount != expected_amount
                or result.currency != money.currency
                or not result.capture_id
            ):
                raise RuntimeError(
                    "PayPal capture response did not match the authorized payment"
                )

            return self._store.mark_captured(
                payment_id,
                result.capture_id,
                now=self._clock(),
            )

    def _execute_if_reserved(self, record: PaymentRecord) -> PaymentRecord:

        if record.status is not PaymentStatus.RESERVED:
            return record
        self._store.assert_audit_healthy()

        if record.payment_channel is PaymentChannel.PAYPAL:
            if record.paypal_order_id:
                return self._complete_paypal_payment(
                    record.payment_id,
                    record.paypal_order_id,
                )

            lock = self._locks[hash(record.payment_id) % _LOCK_STRIPES]
            order_id: str | None = None

            with lock:
                current = self._store.get_payment(record.payment_id)

                if current.status is not PaymentStatus.RESERVED:
                    return current

                if current.paypal_order_id:
                    order_id = current.paypal_order_id
                else:
                    return self._create_paypal_checkout(current)

            # Do not acquire the same non-reentrant lock recursively.
            return self._complete_paypal_payment(
                record.payment_id,
                order_id,
            )

        lock = self._locks[hash(record.payment_id) % _LOCK_STRIPES]
        with lock:
            current = self._store.get_payment(record.payment_id)
            if current.status is not PaymentStatus.RESERVED:
                return current

            try:
                result = self._executor.execute(current)
            except ExecutionError as exc:
                log.warning("payment failed payment_id=%s error_type=%s", current.payment_id, type(exc).__name__)
                return self._store.mark_failed(
                    current.payment_id,
                    now=self._clock(),
                )
            except Exception as exc:
                log.error("payment executor crashed payment_id=%s error_type=%s", current.payment_id, type(exc).__name__)
                raise

            if result.order_id:
                self._store.attach_order(
                    current.payment_id,
                    result.order_id,
                    now=self._clock(),
                )

            return self._store.mark_captured(
                current.payment_id,
                result.capture_id,
                now=self._clock(),
            )
