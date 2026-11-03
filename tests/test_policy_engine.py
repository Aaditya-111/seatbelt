import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from seatbelt.mandate import Mandate
from seatbelt.paypal.models import Money
from seatbelt.policy import (
    PaymentRequest,
    PolicyConfig,
    ReasonCode,
    RiskSignal,
    Severity,
    Verdict,
    evaluate,
)

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
D = Decimal


def mandate(**kw) -> Mandate:
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


def request(amount="20", **kw) -> PaymentRequest:
    base = dict(
        request_id="req-1",
        agent_id="agent-1",
        payee="shop-a",
        money=Money(amount=amount, currency=kw.pop("currency", "USD")),
        description="test",
    )
    base.update(kw)
    return PaymentRequest(**base)


def run(req=None, m=None, committed="0", **kw):
    return evaluate(m or mandate(), req or request(), committed=D(committed), now=NOW, **kw)


def codes(decision):
    return {r.code for r in decision.reasons}


# ---------- the happy path and its boundaries ----------
def test_small_payment_to_approved_payee_is_allowed():
    d = run()
    assert d.verdict is Verdict.ALLOW
    assert ReasonCode.WITHIN_MANDATE in codes(d)


def test_amount_equal_to_threshold_is_still_allowed_but_one_cent_over_needs_approval():
    assert run(request("40")).verdict is Verdict.ALLOW
    d = run(request("40.01"))
    assert d.verdict is Verdict.REQUIRE_APPROVAL
    assert ReasonCode.ABOVE_APPROVAL_THRESHOLD in codes(d)


def test_zero_threshold_always_asks():
    assert run(m=mandate(approval_threshold="0")).verdict is Verdict.REQUIRE_APPROVAL


def test_per_payment_limit_boundary():
    assert run(request("100")).verdict is not Verdict.DENY
    d = run(request("100.01"))
    assert d.verdict is Verdict.DENY
    assert ReasonCode.EXCEEDS_PER_PAYMENT_LIMIT in codes(d)


def test_total_limit_boundary_uses_committed_spend():
    # 250 already spent, 50 left. 50 fits exactly (and needs approval, it's near the limit).
    d = run(request("50"), committed="250")
    assert d.verdict is Verdict.REQUIRE_APPROVAL
    # 50.01 does not fit.
    d = run(request("50.01"), committed="250")
    assert d.verdict is Verdict.DENY
    assert ReasonCode.EXCEEDS_TOTAL_LIMIT in codes(d)
    assert d.remaining_budget == D("50")


def test_budget_alert_threshold_asks_a_human():
    # 200 + 30 = 230 <= 80% of 300 (240): fine.  200 + 45 = 245 > 240: ask.
    assert run(request("30"), committed="200").verdict is Verdict.ALLOW
    d = run(request("45"), committed="200")
    assert d.verdict is Verdict.REQUIRE_APPROVAL
    assert ReasonCode.NEAR_BUDGET_LIMIT in codes(d)


def test_custom_budget_alert_ratio():
    cfg = PolicyConfig(budget_alert_ratio=D("0.5"))
    assert run(request("30"), committed="130", config=cfg).verdict is Verdict.REQUIRE_APPROVAL


@pytest.mark.parametrize("bad", ["0", "-0.1", "1.5"])
def test_invalid_budget_alert_ratio_rejected(bad):
    with pytest.raises(ValueError):
        PolicyConfig(budget_alert_ratio=D(bad))


# ---------- identity, payee, currency, time ----------
def test_unknown_payee_denied_and_payee_matching_ignores_case_and_spaces():
    assert run(request(payee="  SHOP-B ")).verdict is Verdict.ALLOW
    d = run(request(payee="evil-shop"))
    assert d.verdict is Verdict.DENY
    assert ReasonCode.PAYEE_NOT_ALLOWED in codes(d)


def test_lookalike_payees_are_denied():
    for sneaky in ["shop-a.evil", "shop-aa", "shop_a", "shop-a "]:
        d = run(request(payee=sneaky))
        if sneaky.strip() == "shop-a":
            assert d.verdict is Verdict.ALLOW
        else:
            assert d.verdict is Verdict.DENY, sneaky


def test_wrong_agent_denied():
    d = run(request(agent_id="agent-2"))
    assert d.verdict is Verdict.DENY
    assert ReasonCode.AGENT_MISMATCH in codes(d)


def test_wrong_currency_denied():
    d = run(request("20", currency="EUR"))
    assert d.verdict is Verdict.DENY
    assert ReasonCode.CURRENCY_MISMATCH in codes(d)


def test_expired_and_not_yet_valid_mandates_denied():
    m = mandate()
    late = evaluate(m, request(), committed=D(0), now=m.expires_at)
    assert late.verdict is Verdict.DENY and ReasonCode.MANDATE_EXPIRED in codes(late)
    early = evaluate(m, request(), committed=D(0), now=m.issued_at - timedelta(minutes=5))
    assert early.verdict is Verdict.DENY and ReasonCode.MANDATE_NOT_YET_VALID in codes(early)


# ---------- rounding: judge what PayPal will actually charge ----------
def test_amount_is_judged_after_paypal_rounding():
    assert run(request("100.004")).verdict is not Verdict.DENY  # rounds to 100.00
    d = run(request("100.005"))  # rounds up to 100.01
    assert d.verdict is Verdict.DENY
    assert d.amount == D("100.01")


def test_amount_that_rounds_to_zero_cannot_even_be_requested():
    with pytest.raises(ValidationError):
        request("0.001")


# ---------- risk signals ----------
def sig(sev):
    return RiskSignal(code="test_signal", severity=sev, message="something odd")


def test_high_risk_signal_denies_even_a_tiny_payment():
    d = run(request(risk_signals=(sig(Severity.HIGH),)))
    assert d.verdict is Verdict.DENY


def test_medium_risk_signal_asks_a_human():
    d = run(request(risk_signals=(sig(Severity.MEDIUM),)))
    assert d.verdict is Verdict.REQUIRE_APPROVAL


def test_low_risk_signal_is_informational_only():
    d = run(request(risk_signals=(sig(Severity.LOW),)))
    assert d.verdict is Verdict.ALLOW
    assert any(r.effect == "info" and r.code is ReasonCode.RISK_SIGNAL for r in d.reasons)


# ---------- precedence and explanations ----------
def test_deny_beats_approval_and_all_reasons_are_reported():
    d = run(request("500", payee="evil"))
    assert d.verdict is Verdict.DENY
    assert {
        ReasonCode.PAYEE_NOT_ALLOWED,
        ReasonCode.EXCEEDS_PER_PAYMENT_LIMIT,
        ReasonCode.ABOVE_APPROVAL_THRESHOLD,
    } <= codes(d)
    text = d.explain()
    assert text.startswith("DENY") and "evil" in text


def test_explanation_of_a_denial_hides_approval_noise_but_the_record_keeps_it():
    d = run(request("250"))
    assert d.verdict is Verdict.DENY
    assert "without asking" not in d.explain()
    assert ReasonCode.ABOVE_APPROVAL_THRESHOLD in codes(d)


def test_negative_committed_spend_is_a_programming_error():
    with pytest.raises(ValueError):
        run(committed="-1")


def test_decisions_are_immutable():
    d = run()
    with pytest.raises(ValidationError):
        d.verdict = Verdict.ALLOW


# ---------- randomized safety invariants ----------
def test_allow_is_only_ever_returned_for_payments_within_every_limit():
    rng = random.Random(1234)
    payees = ["shop-a", "shop-b", "evil", "shop-a2"]
    for _ in range(3000):
        m = mandate()
        committed = D(rng.randint(0, 40000)) / 100
        req = request(
            amount=str(D(rng.randint(1, 60000)) / 100),
            payee=rng.choice(payees),
            agent_id=rng.choice(["agent-1", "agent-1", "other"]),
            currency=rng.choice(["USD", "USD", "EUR"]),
        )
        d = evaluate(m, req, committed=committed, now=NOW)
        if d.verdict is Verdict.ALLOW:
            assert req.agent_id == m.agent_id
            assert req.money.currency == m.currency
            assert req.payee in m.allowed_payees
            assert d.amount <= m.per_payment_limit
            assert committed + d.amount <= m.total_limit
            assert d.amount <= m.approval_threshold
            assert committed + d.amount <= m.total_limit * D("0.8")