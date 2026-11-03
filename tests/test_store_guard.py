from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from seatbelt.errors import (
    IdempotencyConflictError,
    InvalidTransitionError,
    MandateExpiredError,
    MandateRevokedError,
    NotFoundError,
)
from seatbelt.mandate import Mandate
from seatbelt.paypal.models import Money
from seatbelt.policy import PaymentRequest, Verdict
from seatbelt.store import Database, GuardStore, PaymentStatus

KEY = "k" * 40
NOW = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
D = Decimal


def make_mandate(**kw) -> Mandate:
    base = dict(
        agent_id="agent-1",
        currency="USD",
        per_payment_limit="100",
        total_limit="300",
        approval_threshold="40",
        allowed_payees=["shop-a", "shop-b"],
        issued_at=NOW - timedelta(minutes=5),
        expires_at=NOW + timedelta(hours=1),
    )
    base.update(kw)
    return Mandate(**base)


def req(request_id="r1", amount="20", payee="shop-a", **kw) -> PaymentRequest:
    return PaymentRequest(
        request_id=request_id,
        agent_id=kw.pop("agent_id", "agent-1"),
        payee=payee,
        money=Money(amount=amount, currency="USD"),
        **kw,
    )


@pytest.fixture
def store(tmp_path):
    db = Database(tmp_path / "guard.db")
    db.initialize()
    return GuardStore(db, KEY)


@pytest.fixture
def mandate(store):
    m = make_mandate()
    store.register_mandate(m, "token-placeholder", now=NOW)
    return m


def submit(store, mandate, **kw):
    return store.submit_payment(mandate, req(**kw), now=NOW)


# ---------------- verdicts become statuses ----------------
def test_allowed_payment_is_reserved(store, mandate):
    p = submit(store, mandate)
    assert p.verdict is Verdict.ALLOW and p.status is PaymentStatus.RESERVED


def test_payment_above_threshold_waits_for_a_human(store, mandate):
    p = submit(store, mandate, amount="75")
    assert p.verdict is Verdict.REQUIRE_APPROVAL and p.status is PaymentStatus.PENDING_APPROVAL


def test_denied_payment_reserves_nothing(store, mandate):
    p = submit(store, mandate, payee="evil-shop")
    assert p.status is PaymentStatus.DENIED
    assert store.get_mandate(mandate.mandate_id).committed == 0


def test_unregistered_mandate_is_refused(store):
    with pytest.raises(NotFoundError):
        store.submit_payment(make_mandate(), req(), now=NOW)


# ---------------- budget accounting ----------------
def test_reservations_count_against_later_payments(store, mandate):
    for i in range(3):
        assert submit(store, mandate, request_id=f"a{i}", amount="30").status is (
            PaymentStatus.RESERVED
        )
    assert store.get_mandate(mandate.mandate_id).committed == D("90")
    p = submit(store, mandate, request_id="big", amount="100")  # over the 40 threshold
    assert p.status is PaymentStatus.PENDING_APPROVAL
    p = submit(store, mandate, request_id="too-much", amount="100")  # 290: fits, but asks
    assert p.status is PaymentStatus.PENDING_APPROVAL
    p = submit(store, mandate, request_id="over", amount="20")  # 310 > 300
    assert p.status is PaymentStatus.DENIED


def test_rejecting_releases_the_budget(store, mandate):
    held = submit(store, mandate, request_id="h", amount="100")
    submit(store, mandate, request_id="h2", amount="100")
    assert submit(store, mandate, request_id="x", amount="101").status is PaymentStatus.DENIED
    store.reject_payment(held.payment_id, "boss", "not needed", now=NOW)
    assert store.get_mandate(mandate.mandate_id).committed == D("100")
    assert submit(store, mandate, request_id="y", amount="100").status is not PaymentStatus.DENIED


def test_failed_payment_releases_the_budget(store, mandate):
    p = submit(store, mandate, amount="30")
    store.mark_failed(p.payment_id, "PayPal said no", now=NOW)
    assert store.get_mandate(mandate.mandate_id).committed == 0


# ---------------- idempotency ----------------
def test_same_request_twice_returns_the_same_payment_and_reserves_once(store, mandate):
    a = submit(store, mandate, request_id="dup", amount="30")
    b = submit(store, mandate, request_id="dup", amount="30")
    assert a.payment_id == b.payment_id
    assert store.get_mandate(mandate.mandate_id).committed == D("30")
    assert len(store.list_payments()) == 1


def test_reusing_a_request_id_with_different_details_is_refused(store, mandate):
    submit(store, mandate, request_id="dup", amount="30")
    with pytest.raises(IdempotencyConflictError):
        submit(store, mandate, request_id="dup", amount="31")
    with pytest.raises(IdempotencyConflictError):
        submit(store, mandate, request_id="dup", amount="30", payee="shop-b")


def test_a_denied_request_replayed_stays_denied(store, mandate):
    a = submit(store, mandate, request_id="d", payee="evil")
    b = submit(store, mandate, request_id="d", payee="evil")
    assert a.payment_id == b.payment_id and b.status is PaymentStatus.DENIED


# ---------------- approvals and the state machine ----------------
def test_full_happy_lifecycle(store, mandate):
    p = submit(store, mandate, amount="75")
    p = store.approve_payment(p.payment_id, "boss@example.com", now=NOW)
    assert p.status is PaymentStatus.RESERVED and p.decided_by == "boss@example.com"
    p = store.attach_order(p.payment_id, "ORDER123", now=NOW)
    assert p.paypal_order_id == "ORDER123"
    p = store.mark_captured(p.payment_id, "CAP456", now=NOW)
    assert p.status is PaymentStatus.CAPTURED and p.paypal_capture_id == "CAP456"
    assert store.get_mandate(mandate.mandate_id).committed == D("75")


@pytest.mark.parametrize(
    "setup, action",
    [
        ("pending", lambda s, pid: s.mark_captured(pid, "C1", now=NOW)),
        ("pending", lambda s, pid: s.attach_order(pid, "O1", now=NOW)),
        ("pending", lambda s, pid: s.mark_failed(pid, "x", now=NOW)),
        ("reserved", lambda s, pid: s.approve_payment(pid, "boss", now=NOW)),
        ("reserved", lambda s, pid: s.reject_payment(pid, "boss", now=NOW)),
        ("denied", lambda s, pid: s.approve_payment(pid, "boss", now=NOW)),
        ("denied", lambda s, pid: s.mark_captured(pid, "C1", now=NOW)),
    ],
)
def test_illegal_transitions_are_refused(store, mandate, setup, action):
    kwargs = {
        "pending": dict(amount="75"),
        "reserved": dict(amount="10"),
        "denied": dict(payee="evil"),
    }[setup]
    p = submit(store, mandate, **kwargs)
    with pytest.raises(InvalidTransitionError):
        action(store, p.payment_id)


def test_terminal_states_stay_terminal(store, mandate):
    p = submit(store, mandate, amount="10")
    store.mark_captured(p.payment_id, "C1", now=NOW)
    for action in (
        lambda: store.mark_captured(p.payment_id, "C2", now=NOW),
        lambda: store.mark_failed(p.payment_id, "x", now=NOW),
        lambda: store.approve_payment(p.payment_id, "boss", now=NOW),
    ):
        with pytest.raises(InvalidTransitionError):
            action()


def test_double_approval_is_refused(store, mandate):
    p = submit(store, mandate, amount="75")
    store.approve_payment(p.payment_id, "boss", now=NOW)
    with pytest.raises(InvalidTransitionError):
        store.approve_payment(p.payment_id, "boss", now=NOW)


def test_approving_after_the_mandate_expired_cancels_instead(store, mandate):
    p = submit(store, mandate, amount="75")
    with pytest.raises(MandateExpiredError):
        store.approve_payment(p.payment_id, "boss", now=NOW + timedelta(hours=2))
    after = store.get_payment(p.payment_id)
    assert after.status is PaymentStatus.CANCELLED
    assert store.get_mandate(mandate.mandate_id).committed == 0


def test_unknown_payment_is_not_found(store):
    with pytest.raises(NotFoundError):
        store.approve_payment("nope", "boss", now=NOW)


@pytest.mark.parametrize("bad", ["", "   ", "a b", "x" * 65, "evil\nactor", "a;drop"])
def test_actor_names_are_validated(store, mandate, bad):
    p = submit(store, mandate, amount="75")
    with pytest.raises(ValueError):
        store.approve_payment(p.payment_id, bad, now=NOW)


# ---------------- kill switch ----------------
def test_revoking_cancels_open_payments_but_not_captured_ones(store, mandate):
    done = submit(store, mandate, request_id="done", amount="10")
    store.mark_captured(done.payment_id, "C1", now=NOW)
    held = submit(store, mandate, request_id="held", amount="75")
    reserved = submit(store, mandate, request_id="res", amount="10")

    assert store.revoke_mandate(mandate.mandate_id, "admin", now=NOW) == 2
    assert store.get_payment(done.payment_id).status is PaymentStatus.CAPTURED
    assert store.get_payment(held.payment_id).status is PaymentStatus.CANCELLED
    assert store.get_payment(reserved.payment_id).status is PaymentStatus.CANCELLED
    assert store.get_mandate(mandate.mandate_id).committed == D("10")
    assert store.get_mandate(mandate.mandate_id).revoked_at is not None


def test_revoked_mandate_accepts_no_new_payments_and_revoking_twice_is_harmless(store, mandate):
    store.revoke_mandate(mandate.mandate_id, "admin", now=NOW)
    assert store.revoke_mandate(mandate.mandate_id, "admin", now=NOW) == 0
    with pytest.raises(MandateRevokedError):
        submit(store, mandate)


# ---------------- concurrency: the whole point of this step ----------------
def test_concurrent_payments_can_never_overspend_the_budget(tmp_path):
    db = Database(tmp_path / "race.db")
    db.initialize()
    store = GuardStore(db, KEY)
    m = make_mandate(total_limit="300", per_payment_limit="100", approval_threshold="40")
    store.register_mandate(m, "t", now=NOW)

    def attempt(i):
        return store.submit_payment(m, req(request_id=f"c{i}", amount="30"), now=NOW)

    with ThreadPoolExecutor(max_workers=24) as pool:
        results = list(pool.map(attempt, range(24)))

    holding = [r for r in results if r.status is not PaymentStatus.DENIED]
    assert len(holding) == 10  # exactly 300 / 30, never 11
    assert sum(r.amount for r in holding) == D("300")
    assert store.get_mandate(m.mandate_id).committed == D("300")
    assert store.verify_audit().ok  # and the log stayed consistent under contention


# ---------------- audit trail ----------------
def test_every_step_is_audited_and_the_chain_verifies(store, mandate):
    p = submit(store, mandate, amount="75")
    store.approve_payment(p.payment_id, "boss", now=NOW)
    store.attach_order(p.payment_id, "O1", now=NOW)
    store.mark_captured(p.payment_id, "C1", now=NOW)
    events = [e["event"] for e in reversed(store.list_audit())]
    assert events == [
        "mandate.registered",
        "payment.submitted",
        "payment.approved",
        "payment.order_created",
        "payment.captured",
    ]
    status = store.verify_audit()
    assert status.ok and status.entries == 5


def test_denials_are_audited_with_their_reasons(store, mandate):
    submit(store, mandate, payee="evil")
    entry = store.list_audit(limit=1)[0]
    assert entry["event"] == "payment.submitted"
    assert "payee_not_allowed" in entry["data"]["reason_codes"]
    assert entry["data"]["verdict"] == "deny"


def test_registering_a_mandate_twice_logs_once(store, mandate):
    store.register_mandate(mandate, "t", now=NOW)
    assert [e["event"] for e in store.list_audit()].count("mandate.registered") == 1


def test_list_payments_filters_and_orders_newest_first(store, mandate):
    a = submit(store, mandate, request_id="a", amount="10")
    b = submit(store, mandate, request_id="b", payee="evil")
    assert [p.payment_id for p in store.list_payments()] == [b.payment_id, a.payment_id]
    assert [p.payment_id for p in store.list_payments(status=PaymentStatus.DENIED)] == [
        b.payment_id
    ]
    assert store.list_payments(mandate_id="other") == []