from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import threading

import pytest
from pydantic import ValidationError

from seatbelt.errors import (
    ExecutionError,
    IdempotencyConflictError,
    MandateError,
    MandateExpiredError,
    MandateRevokedError,
    MandateSignatureError,
)
from seatbelt.service import ExecutionResult, FakeExecutor, GuardService
from seatbelt.store import Database, GuardStore, PaymentStatus

KEY = "k" * 40
START = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
D = Decimal


class Clock:
    def __init__(self):
        self.now = START

    def __call__(self):
        return self.now

    def advance(self, **kw):
        self.now += timedelta(**kw)


def build(tmp_path, executor=None, name="g.db", clock=None):
    db = Database(tmp_path / name)
    db.initialize()
    clock = clock or Clock()
    executor = executor or FakeExecutor()
    svc = GuardService(
        GuardStore(db, KEY), executor, KEY, max_mandate_ttl=timedelta(hours=24), clock=clock
    )
    return svc, executor, clock


@pytest.fixture
def env(tmp_path):
    return build(tmp_path)


def issue(svc, **kw):
    args = dict(
        agent_id="agent-1",
        currency="USD",
        per_payment_limit="100",
        total_limit="300",
        approval_threshold="40",
        allowed_payees=["shop-a", "shop-b"],
        ttl=timedelta(hours=1),
    )
    args.update(kw)
    return svc.issue_mandate(**args)


def pay(svc, token, request_id="r1", payee="shop-a", amount="20", currency="USD", **kw):
    return svc.submit_payment(
        token, request_id=request_id, payee=payee, amount=amount, currency=currency, **kw
    )


# ---------------- mandates and authentication ----------------
def test_issued_mandate_is_registered_and_its_token_authenticates(env):
    svc, _, _ = env
    mandate, token = issue(svc)
    assert svc.authenticate_agent(token) == mandate
    assert svc.get_mandate(mandate.mandate_id).committed == 0


def test_ttl_above_the_configured_maximum_is_refused(env):
    svc, _, _ = env
    with pytest.raises(MandateError):
        issue(svc, ttl=timedelta(hours=25))


def test_tampered_token_is_rejected(env):
    svc, _, _ = env
    _, token = issue(svc)
    payload, sig = token.split(".")
    flipped = ("A" if payload[10] != "A" else "B").join([payload[:10], payload[11:]])
    with pytest.raises(MandateSignatureError):
        svc.authenticate_agent(f"{flipped}.{sig}")


def test_expired_token_is_rejected(env):
    svc, _, clock = env
    _, token = issue(svc, ttl=timedelta(minutes=30))
    clock.advance(minutes=31)
    with pytest.raises(MandateExpiredError):
        svc.authenticate_agent(token)


def test_revoked_token_is_rejected(env):
    svc, _, _ = env
    mandate, token = issue(svc)
    svc.revoke_mandate(mandate.mandate_id, "admin")
    with pytest.raises(MandateRevokedError):
        svc.authenticate_agent(token)
    with pytest.raises(MandateRevokedError):
        pay(svc, token)


def test_validly_signed_but_unregistered_mandate_is_not_recognised(tmp_path):
    svc_a, _, clock = build(tmp_path, name="a.db")
    svc_b, _, _ = build(tmp_path, name="b.db", clock=clock)  # same key, different database
    _, token = issue(svc_a)
    with pytest.raises(MandateSignatureError, match="not recognised"):
        svc_b.authenticate_agent(token)


# ---------------- paying ----------------
def test_allowed_payment_is_executed_exactly_once_and_captured(env):
    svc, executor, _ = env
    _, token = issue(svc)
    p = pay(svc, token, amount="25")
    assert p.status is PaymentStatus.CAPTURED
    assert p.paypal_order_id and p.paypal_capture_id
    assert executor.executed == [p.payment_id]


def test_payment_needing_approval_does_not_execute_until_approved(env):
    svc, executor, _ = env
    _, token = issue(svc)
    p = pay(svc, token, amount="75")
    assert p.status is PaymentStatus.PENDING_APPROVAL and executor.executed == []
    p = svc.approve_payment(p.payment_id, "boss@example.com")
    assert p.status is PaymentStatus.CAPTURED and executor.executed == [p.payment_id]


def test_rejected_payment_never_executes_and_releases_budget(env):
    svc, executor, _ = env
    mandate, token = issue(svc)
    p = pay(svc, token, amount="75")
    svc.reject_payment(p.payment_id, "boss", "no thanks")
    assert svc.get_payment(p.payment_id).status is PaymentStatus.REJECTED
    assert executor.executed == []
    assert svc.get_mandate(mandate.mandate_id).committed == 0


def test_denied_payment_never_executes(env):
    svc, executor, _ = env
    _, token = issue(svc)
    p = pay(svc, token, payee="evil-shop")
    assert p.status is PaymentStatus.DENIED and executor.executed == []


def test_agent_identity_comes_from_the_mandate(env):
    svc, _, _ = env
    mandate, token = issue(svc, agent_id="agent-77")
    assert pay(svc, token).agent_id == "agent-77" == mandate.agent_id


def test_amounts_are_judged_after_paypal_rounding(env):
    svc, _, _ = env
    _, token = issue(svc)
    assert pay(svc, token, request_id="a", amount="40.004").status is PaymentStatus.CAPTURED
    held = pay(svc, token, request_id="b", amount="40.005")  # rounds to 40.01 > threshold
    assert held.status is PaymentStatus.PENDING_APPROVAL and held.amount == D("40.01")


def test_amount_that_rounds_to_zero_is_refused(env):
    svc, _, _ = env
    _, token = issue(svc)
    with pytest.raises(ValidationError):
        pay(svc, token, amount="0.001")


# ---------------- failures ----------------
def test_executor_failure_marks_the_payment_failed_and_frees_the_budget(tmp_path):
    svc, _, _ = build(tmp_path, FakeExecutor(fail_for_payees={"shop-b"}))
    mandate, token = issue(svc)
    p = pay(svc, token, payee="shop-b", amount="30")
    assert p.status is PaymentStatus.FAILED and "simulated failure" in p.failure
    assert svc.get_mandate(mandate.mandate_id).committed == 0


class CrashOnce:
    def __init__(self):
        self.calls = 0

    def execute(self, payment):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("super secret internal detail")
        return ExecutionResult(capture_id="CAP-AFTER-RETRY", order_id="ORD-AFTER-RETRY")


def test_executor_crash_leaves_payment_reserved_and_retry_completes_it(tmp_path):
    svc, executor, _ = build(tmp_path, CrashOnce())
    mandate, token = issue(svc)
    with pytest.raises(RuntimeError):
        pay(svc, token, amount="30")
    stuck = svc.list_payments()[0]
    assert stuck.status is PaymentStatus.RESERVED  # budget still held
    assert svc.get_mandate(mandate.mandate_id).committed == D("30")

    done = svc.retry_payment(stuck.payment_id)
    assert done.status is PaymentStatus.CAPTURED and done.paypal_capture_id == "CAP-AFTER-RETRY"
    assert executor.calls == 2


def test_retry_of_a_finished_payment_does_nothing(env):
    svc, executor, _ = env
    _, token = issue(svc)
    p = pay(svc, token)
    again = svc.retry_payment(p.payment_id)
    assert again.status is PaymentStatus.CAPTURED and executor.executed == [p.payment_id]


# ---------------- idempotency and concurrency ----------------
def test_replaying_a_request_does_not_pay_twice(env):
    svc, executor, _ = env
    _, token = issue(svc)
    a = pay(svc, token, request_id="dup")
    b = pay(svc, token, request_id="dup")
    assert a.payment_id == b.payment_id and len(executor.executed) == 1


def test_reusing_a_request_id_with_different_details_conflicts(env):
    svc, _, _ = env
    _, token = issue(svc)
    pay(svc, token, request_id="dup", amount="20")
    with pytest.raises(IdempotencyConflictError):
        pay(svc, token, request_id="dup", amount="21")


def test_simultaneous_identical_requests_pay_exactly_once(tmp_path):
    svc, executor, _ = build(tmp_path)
    _, token = issue(svc)

    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(lambda _: pay(svc, token, request_id="same"), range(12)))

    assert len({r.payment_id for r in results}) == 1
    assert all(r.status is PaymentStatus.CAPTURED for r in results)
    assert len(executor.executed) == 1


def test_simultaneous_distinct_requests_never_overspend(tmp_path):
    svc, executor, _ = build(tmp_path)
    mandate, token = issue(svc, total_limit="300")

    with ThreadPoolExecutor(max_workers=24) as pool:
        results = list(
            pool.map(lambda i: pay(svc, token, request_id=f"c{i}", amount="30"), range(24))
        )

    spent = sum(r.amount for r in results if r.status is PaymentStatus.CAPTURED)
    assert spent <= D("300")
    assert svc.get_mandate(mandate.mandate_id).committed <= D("300")
    assert len(executor.executed) == len([r for r in results if r.status is PaymentStatus.CAPTURED])
    assert svc.verify_audit().ok


def test_executor_error_type_is_exported_for_implementers():
    assert issubclass(ExecutionError, Exception)


from seatbelt.paypal.models import CaptureResult, Order, OrderPurchaseUnit


class FakePayPal:
    """In-memory PayPal simulator for service lifecycle tests."""

    def __init__(
        self,
        *,
        merchant_id="MERCHANT-1",
        amount="20.00",
        currency="USD",
        reference_id=None,
        lose_capture_response=False,
    ):
        self.merchant_id = merchant_id
        self.amount = Decimal(amount)
        self.currency = currency
        self.reference_override = reference_id
        self.reference_id = None
        self.lose_capture_response = lose_capture_response
        self.created = []
        self.captured = []
        self.get_calls = 0
        self.completed = False
        self.order_status = "APPROVED"
        self.order_id = "ORDER-TEST-1"
        self.capture_id = "CAPTURE-TEST-1"

    def create_order(self, money, *, description, reference_id, request_id=None):
        self.created.append(request_id)
        self.reference_id = reference_id
        return Order(
            id=self.order_id,
            status="PAYER_ACTION_REQUIRED",
            approve_url="https://www.sandbox.paypal.com/checkoutnow?token=ORDER-TEST-1",
            purchase_units=(
                OrderPurchaseUnit(
                    reference_id=reference_id,
                    amount=Decimal(money.to_paypal_value()),
                    currency_code=money.currency,
                    merchant_id=self.merchant_id,
                ),
            ),
        )

    def get_order(self, order_id):
        assert order_id == self.order_id
        self.get_calls += 1

        return Order(
            id=self.order_id,
            status="COMPLETED" if self.completed else self.order_status,
            purchase_units=(
                OrderPurchaseUnit(
                    reference_id=self.reference_override or self.reference_id,
                    amount=self.amount,
                    currency_code=self.currency,
                    merchant_id=self.merchant_id,
                    capture_id=self.capture_id if self.completed else None,
                    capture_amount=self.amount if self.completed else None,
                    capture_currency=self.currency if self.completed else None,
                ),
            ),
        )

    def capture_order(self, order_id, *, request_id=None):
        assert order_id == self.order_id
        self.captured.append(request_id)
        self.completed = True

        if self.lose_capture_response:
            self.lose_capture_response = False
            raise RuntimeError("simulated lost capture response")

        return CaptureResult(
            order_id=self.order_id,
            status="COMPLETED",
            capture_id=self.capture_id,
            amount=self.amount,
            currency=self.currency,
        )


def build_paypal(tmp_path, paypal=None, name="paypal.db"):
    paypal = paypal or FakePayPal()
    db = Database(tmp_path / name)
    db.initialize()
    clock = Clock()
    svc = GuardService(
        GuardStore(db, KEY),
        FakeExecutor(),
        KEY,
        max_mandate_ttl=timedelta(hours=24),
        clock=clock,
        paypal_client=paypal,
        paypal_expected_merchant_id="MERCHANT-1",
    )
    return svc, paypal, clock


def submit_paypal(svc, token, request_id="paypal-r1", amount="20"):
    return svc.submit_paypal_payment(
        token,
        request_id=request_id,
        payee="shop-a",
        amount=amount,
        currency="USD",
        description="Test purchase",
    )


def test_paypal_payment_creates_checkout_and_persists_order(tmp_path):
    svc, paypal, _ = build_paypal(tmp_path)
    _, token = issue(svc)

    payment = submit_paypal(svc, token)

    assert payment.status is PaymentStatus.AWAITING_PAYER
    assert payment.payment_channel.value == "paypal"
    assert payment.paypal_order_id == paypal.order_id
    assert payment.paypal_approve_url.startswith(
        "https://www.sandbox.paypal.com/checkoutnow"
    )
    assert len(paypal.created) == 1
    assert paypal.created[0]


def test_paypal_return_verifies_order_and_captures_once(tmp_path):
    svc, paypal, _ = build_paypal(tmp_path)
    _, token = issue(svc)
    payment = submit_paypal(svc, token)

    completed = svc.process_paypal_return(paypal.order_id)

    assert completed.status is PaymentStatus.CAPTURED
    assert completed.paypal_capture_id == paypal.capture_id
    assert len(paypal.captured) == 1
    assert paypal.captured[0]


def test_duplicate_paypal_return_does_not_capture_twice(tmp_path):
    svc, paypal, _ = build_paypal(tmp_path)
    _, token = issue(svc)
    payment = submit_paypal(svc, token)

    first = svc.process_paypal_return(paypal.order_id)
    second = svc.process_paypal_return(paypal.order_id)

    assert first.status is second.status is PaymentStatus.CAPTURED
    assert first.payment_id == second.payment_id == payment.payment_id
    assert len(paypal.captured) == 1


def test_concurrent_paypal_returns_capture_only_once(tmp_path):
    svc, paypal, _ = build_paypal(tmp_path)
    _, token = issue(svc)
    payment = submit_paypal(svc, token)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(
                lambda _: svc.process_paypal_return(paypal.order_id),
                range(8),
            )
        )

    assert all(r.payment_id == payment.payment_id for r in results)
    assert all(r.status is PaymentStatus.CAPTURED for r in results)
    assert len(paypal.captured) == 1

def test_separate_services_concurrently_capture_with_same_idempotency_key(
    tmp_path,
):
    class IdempotentConcurrentPayPal(FakePayPal):
        def __init__(self):
            super().__init__()
            self.capture_barrier = threading.Barrier(2)
            self.capture_lock = threading.Lock()
            self.capture_results = {}
            self.capture_requests = []

        def capture_order(self, order_id, *, request_id=None):
            # Force both independent services to reach the provider together.
            self.capture_barrier.wait(timeout=10)

            with self.capture_lock:
                self.capture_requests.append(request_id)

                # Simulate PayPal deduplicating the same request ID.
                if request_id not in self.capture_results:
                    result = super().capture_order(
                        order_id,
                        request_id=request_id,
                    )
                    self.capture_results[request_id] = result

                return self.capture_results[request_id]

    paypal = IdempotentConcurrentPayPal()
    svc1, paypal, clock = build_paypal(tmp_path, paypal)

    _, token = issue(svc1)
    payment = submit_paypal(svc1, token)

    # Put the payment in RESERVED, as it would be after verified approval.
    svc1._store.mark_payer_approved(
        payment.payment_id,
        now=svc1._clock(),
    )

    # A second, independent service instance shares only the database
    # and PayPal provider—not the first instance's in-process locks.
    db2 = Database(tmp_path / "paypal.db")
    db2.initialize()

    svc2 = GuardService(
        GuardStore(db2, KEY),
        FakeExecutor(),
        KEY,
        max_mandate_ttl=timedelta(hours=24),
        clock=clock,
        paypal_client=paypal,
        paypal_expected_merchant_id="MERCHANT-1",
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(svc1.process_paypal_return, paypal.order_id),
            pool.submit(svc2.process_paypal_return, paypal.order_id),
        ]
        results = [future.result(timeout=20) for future in futures]

    assert all(r.status is PaymentStatus.CAPTURED for r in results)
    assert len(paypal.capture_requests) == 2
    assert len(set(paypal.capture_requests)) == 1
    assert len(paypal.captured) == 1

    final = svc1.get_payment(payment.payment_id)
    assert final.status is PaymentStatus.CAPTURED
    assert final.paypal_capture_id == paypal.capture_id


def test_paypal_capture_timeout_is_reconciled_without_second_capture(tmp_path):
    paypal = FakePayPal(lose_capture_response=True)
    svc, paypal, _ = build_paypal(tmp_path, paypal)
    _, token = issue(svc)
    payment = submit_paypal(svc, token)

    with pytest.raises(RuntimeError, match="lost capture response"):
        svc.process_paypal_return(paypal.order_id)

    stuck = svc.get_payment(payment.payment_id)
    assert stuck.status is PaymentStatus.RESERVED

    recovered = svc.retry_payment(payment.payment_id)

    assert recovered.status is PaymentStatus.CAPTURED
    assert recovered.paypal_capture_id == paypal.capture_id
    assert len(paypal.captured) == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"merchant_id": "ATTACKER-MERCHANT"},
        {"amount": "999.00"},
        {"currency": "EUR"},
        {"reference_id": "another-payment"},
    ],
)
def test_paypal_order_tampering_is_rejected_before_capture(tmp_path, overrides):
    paypal = FakePayPal(**overrides)
    svc, paypal, _ = build_paypal(tmp_path, paypal)
    _, token = issue(svc)
    payment = submit_paypal(svc, token)

    with pytest.raises(ValueError):
        svc.process_paypal_return(paypal.order_id)

    unchanged = svc.get_payment(payment.payment_id)
    assert unchanged.status is PaymentStatus.AWAITING_PAYER
    assert paypal.captured == []


def test_paypal_callback_cannot_resolve_an_unknown_order(tmp_path):
    svc, paypal, _ = build_paypal(tmp_path)

    with pytest.raises(Exception):
        svc.process_paypal_return("UNKNOWN-ORDER")

    assert paypal.get_calls == 0


def test_paypal_retries_reuse_stable_request_ids(tmp_path):
    paypal = FakePayPal(lose_capture_response=True)
    svc, paypal, _ = build_paypal(tmp_path, paypal)
    _, token = issue(svc)
    payment = submit_paypal(svc, token)

    with pytest.raises(RuntimeError):
        svc.process_paypal_return(paypal.order_id)

    svc.retry_payment(payment.payment_id)

    assert len(paypal.created) == 1
    assert len(paypal.captured) == 1


# ---------------- PayPal cancellation lifecycle ----------------

def test_paypal_cancel_verifies_created_order_and_releases_payment(tmp_path):
    svc, paypal, _ = build_paypal(tmp_path)
    _, token = issue(svc)
    payment = submit_paypal(svc, token)
    paypal.order_status = "VOIDED"

    cancelled = svc.process_paypal_cancel(paypal.order_id)

    assert cancelled.payment_id == payment.payment_id
    assert cancelled.status is PaymentStatus.CANCELLED
    assert paypal.get_calls == 1
    assert paypal.captured == []
    assert svc.verify_audit().ok


def test_duplicate_paypal_cancel_is_idempotent(tmp_path):
    svc, paypal, _ = build_paypal(tmp_path)
    _, token = issue(svc)
    payment = submit_paypal(svc, token)
    paypal.order_status = "VOIDED"

    first = svc.process_paypal_cancel(paypal.order_id)
    second = svc.process_paypal_cancel(paypal.order_id)

    assert first.status is second.status is PaymentStatus.CANCELLED
    assert first.payment_id == second.payment_id == payment.payment_id
    assert paypal.get_calls == 1
    assert paypal.captured == []


@pytest.mark.parametrize("order_status", ["APPROVED", "COMPLETED"])
def test_paypal_cancel_rejects_approved_or_completed_order(tmp_path, order_status):
    svc, paypal, _ = build_paypal(tmp_path)
    _, token = issue(svc)
    payment = submit_paypal(svc, token)
    paypal.order_status = order_status
    if order_status == "COMPLETED":
        paypal.completed = True

    with pytest.raises(ValueError, match="cancellable"):
        svc.process_paypal_cancel(paypal.order_id)

    unchanged = svc.get_payment(payment.payment_id)
    assert unchanged.status is PaymentStatus.AWAITING_PAYER
    assert paypal.captured == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"merchant_id": "ATTACKER-MERCHANT"},
        {"amount": "999.00"},
        {"currency": "EUR"},
        {"reference_id": "another-payment"},
    ],
)
def test_paypal_cancel_rejects_tampered_order_before_releasing_payment(
    tmp_path, overrides
):
    paypal = FakePayPal(**overrides)
    svc, paypal, _ = build_paypal(tmp_path, paypal)
    _, token = issue(svc)
    payment = submit_paypal(svc, token)
    paypal.order_status = "CREATED"

    with pytest.raises(ValueError):
        svc.process_paypal_cancel(paypal.order_id)

    unchanged = svc.get_payment(payment.payment_id)
    assert unchanged.status is PaymentStatus.AWAITING_PAYER
    assert paypal.captured == []

def test_paypal_cancel_callback_keeps_reservation_when_order_is_not_voided(tmp_path):
    svc, paypal, _ = build_paypal(tmp_path)
    _, token = issue(svc)
    payment = submit_paypal(svc, token)

    paypal.order_status = "PAYER_ACTION_REQUIRED"

    first = svc.process_paypal_cancel(paypal.order_id)
    second = svc.process_paypal_cancel(paypal.order_id)

    assert first.status is PaymentStatus.AWAITING_PAYER
    assert second.status is PaymentStatus.AWAITING_PAYER
    assert first.payment_id == second.payment_id == payment.payment_id
    assert paypal.get_calls == 2
    assert paypal.captured == []
    assert svc.verify_audit().ok

    events = svc._store.list_audit(limit=500)
    cancellation_events = [
        event for event in events
        if event["event"] == "payment.paypal_cancel_requested"
        and event["subject_id"] == payment.payment_id
    ]
    assert len(cancellation_events) == 1
