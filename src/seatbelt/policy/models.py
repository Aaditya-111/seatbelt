"""Data types for the policy engine: requests going in, decisions coming out."""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from seatbelt.paypal.models import Money

_ID_PATTERN = r"^[A-Za-z0-9_.:-]+$"


class Severity(str, Enum):
    LOW = "low"  # informational only
    MEDIUM = "medium"  # a human must look at it
    HIGH = "high"  # block outright


class RiskSignal(BaseModel):
    """Something suspicious noticed about a request (produced by detectors, e.g. in Step 6)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(min_length=1, max_length=64, pattern=_ID_PATTERN)
    severity: Severity
    message: str = Field(min_length=1, max_length=300)


class PaymentRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: str = Field(min_length=1, max_length=64, pattern=_ID_PATTERN)
    agent_id: str = Field(min_length=1, max_length=64, pattern=_ID_PATTERN)
    payee: str = Field(min_length=1, max_length=128)
    money: Money
    description: str = Field(default="", max_length=500)
    risk_signals: tuple[RiskSignal, ...] = ()

    @field_validator("payee")
    @classmethod
    def _normalise_payee(cls, v: str) -> str:
        v = v.strip().lower()
        if not v:
            raise ValueError("payee must not be blank")
        return v

    @model_validator(mode="after")
    def _amount_must_be_chargeable(self) -> PaymentRequest:
        # Fails here (not later) if the amount would round to zero at PayPal.
        self.money.to_paypal_value()
        return self

    @property
    def charge_amount(self) -> Decimal:
        """The amount PayPal will actually charge, after PayPal's own rounding rules."""
        return Decimal(self.money.to_paypal_value())


class Verdict(str, Enum):
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"


class ReasonCode(str, Enum):
    WITHIN_MANDATE = "within_mandate"
    AGENT_MISMATCH = "agent_mismatch"
    CURRENCY_MISMATCH = "currency_mismatch"
    PAYEE_NOT_ALLOWED = "payee_not_allowed"
    EXCEEDS_PER_PAYMENT_LIMIT = "exceeds_per_payment_limit"
    EXCEEDS_TOTAL_LIMIT = "exceeds_total_limit"
    MANDATE_EXPIRED = "mandate_expired"
    MANDATE_NOT_YET_VALID = "mandate_not_yet_valid"
    ABOVE_APPROVAL_THRESHOLD = "above_approval_threshold"
    NEAR_BUDGET_LIMIT = "near_budget_limit"
    RISK_SIGNAL = "risk_signal"


class Reason(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: ReasonCode
    effect: Literal["deny", "approve", "info"]
    message: str


class Decision(BaseModel):
    model_config = ConfigDict(frozen=True)

    verdict: Verdict
    reasons: tuple[Reason, ...]
    amount: Decimal
    currency: str
    remaining_budget: Decimal  # budget left BEFORE this payment, never negative

    def explain(self) -> str:
        """Plain-language summary for logs and the approval screen."""
        # On a DENY, "needs approval" reasons are noise; they stay in `reasons` for the audit log.
        shown = self.reasons
        if self.verdict is Verdict.DENY:
            shown = tuple(r for r in self.reasons if r.effect != "approve")
        lines = [f"{self.verdict.value.upper()}: {self.amount} {self.currency}"]
        lines += [f"- {r.message}" for r in shown]
        return "\n".join(lines)