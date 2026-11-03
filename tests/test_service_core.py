from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal

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