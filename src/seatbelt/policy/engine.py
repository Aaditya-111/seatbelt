"""The policy engine: decides whether a payment is allowed, needs approval, or is denied.

It is a pure function of (mandate, request, committed spend, time), with no I/O, so it is
easy to test exhaustively. It never stops at the first problem: every rule is evaluated
so the person approving can see the whole picture.

Precedence:  any deny reason  ->  DENY
             else any approve reason  ->  REQUIRE_APPROVAL
             else  ->  ALLOW
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from seatbelt.mandate.models import Mandate
from seatbelt.mandate.signing import CLOCK_SKEW
from seatbelt.policy.models import (
    Decision,
    PaymentRequest,
    Reason,
    ReasonCode,
    Severity,
    Verdict,
)


@dataclass(frozen=True)
class PolicyConfig:
    # A payment that would push total usage above this fraction of total_limit needs approval.
    budget_alert_ratio: Decimal = Decimal("0.8")

    def __post_init__(self) -> None:
        if not (Decimal("0") < self.budget_alert_ratio <= Decimal("1")):
            raise ValueError("budget_alert_ratio must be in (0, 1]")


def evaluate(
    mandate: Mandate,
    request: PaymentRequest,
    *,
    committed: Decimal,
    now: datetime | None = None,
    config: PolicyConfig | None = None,
) -> Decision:
    """Evaluate one payment request against one (already signature-verified) mandate.

    `committed` is the total already spent or reserved under this mandate.
    """
    if committed < 0:
        raise ValueError("committed spend cannot be negative")
    config = config or PolicyConfig()
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)

    amount = request.charge_amount
    cur = mandate.currency
    remaining = max(mandate.total_limit - committed, Decimal("0"))
    reasons: list[Reason] = []

    def deny(code: ReasonCode, msg: str) -> None:
        reasons.append(Reason(code=code, effect="deny", message=msg))

    def approve(code: ReasonCode, msg: str) -> None:
        reasons.append(Reason(code=code, effect="approve", message=msg))

    # ---- hard limits: any of these denies --------------------------------
    if now >= mandate.expires_at:
        deny(ReasonCode.MANDATE_EXPIRED, "The agent's spending permission has expired.")
    elif now < mandate.issued_at - CLOCK_SKEW:
        deny(ReasonCode.MANDATE_NOT_YET_VALID, "The agent's spending permission is not active yet.")

    if request.agent_id != mandate.agent_id:
        deny(ReasonCode.AGENT_MISMATCH, "This permission was issued to a different agent.")

    if request.money.currency != cur:
        deny(
            ReasonCode.CURRENCY_MISMATCH,
            f"Payment is in {request.money.currency} but the permission is for {cur}.",
        )

    if request.payee not in mandate.allowed_payees:
        deny(
            ReasonCode.PAYEE_NOT_ALLOWED,
            f"'{request.payee}' is not on the agent's list of approved payees.",
        )

    if amount > mandate.per_payment_limit:
        deny(
            ReasonCode.EXCEEDS_PER_PAYMENT_LIMIT,
            f"{amount} {cur} is above the per-payment limit of {mandate.per_payment_limit} {cur}.",
        )

    if committed + amount > mandate.total_limit:
        deny(
            ReasonCode.EXCEEDS_TOTAL_LIMIT,
            f"Only {remaining} {cur} of the {mandate.total_limit} {cur} budget is left.",
        )

    # ---- risk signals from detectors --------------------------------------
    for signal in request.risk_signals:
        if signal.severity is Severity.HIGH:
            deny(ReasonCode.RISK_SIGNAL, f"High risk: {signal.message}")
        elif signal.severity is Severity.MEDIUM:
            approve(ReasonCode.RISK_SIGNAL, f"Needs review: {signal.message}")
        else:
            reasons.append(
                Reason(code=ReasonCode.RISK_SIGNAL, effect="info", message=signal.message)
            )

    # ---- soft limits: these ask a human ------------------------------------
    if amount > mandate.approval_threshold:
        approve(
            ReasonCode.ABOVE_APPROVAL_THRESHOLD,
            f"{amount} {cur} is above the {mandate.approval_threshold} {cur} "
            "amount the agent may spend without asking.",
        )

    if committed + amount > mandate.total_limit * config.budget_alert_ratio:
        approve(
            ReasonCode.NEAR_BUDGET_LIMIT,
            f"This payment would use more than {config.budget_alert_ratio:.0%} of the budget.",
        )

    # ---- verdict -----------------------------------------------------------
    if any(r.effect == "deny" for r in reasons):
        verdict = Verdict.DENY
    elif any(r.effect == "approve" for r in reasons):
        verdict = Verdict.REQUIRE_APPROVAL
    else:
        verdict = Verdict.ALLOW
        reasons.append(
            Reason(
                code=ReasonCode.WITHIN_MANDATE,
                effect="info",
                message="Within the agent's limits, approved payee, no risk flags.",
            )
        )

    return Decision(
        verdict=verdict,
        reasons=tuple(reasons),
        amount=amount,
        currency=request.money.currency,
        remaining_budget=remaining,
    )