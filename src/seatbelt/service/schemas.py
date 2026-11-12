"""Request/response bodies for the HTTP API. Strict by design:

  * money travels as a STRING ("12.50"); JSON numbers are rejected (no float surprises)
  * unknown fields are rejected
  * identifiers are pattern-checked here, before they reach any logic
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from seatbelt.mandate import Mandate

MoneyStr = Annotated[str, StringConstraints(pattern=r"^\d{1,12}(\.\d{1,6})?$")]
Currency = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
Ident = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_.:-]{1,64}$")]
Actor = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_.:@+-]{1,64}$")]
PayeeStr = Annotated[str, StringConstraints(min_length=1, max_length=128)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IssueMandateBody(_Strict):
    agent_id: Ident
    currency: Currency = "USD"
    per_payment_limit: MoneyStr
    total_limit: MoneyStr
    approval_threshold: MoneyStr
    allowed_payees: list[PayeeStr] = Field(min_length=1, max_length=100)
    ttl_minutes: int = Field(ge=1, le=60 * 24 * 30)


class MandateIssued(BaseModel):
    mandate: Mandate
    token: str


class PaymentBody(_Strict):
    request_id: Ident
    payee: PayeeStr
    amount: MoneyStr
    currency: Currency
    description: Annotated[str, StringConstraints(max_length=500)] = ""


class ApproveBody(_Strict):
    approver: Actor


class RejectBody(_Strict):
    approver: Actor
    reason: Annotated[str, StringConstraints(max_length=300)] = ""


class RevokeResult(BaseModel):
    payments_cancelled: int


class AuditEntry(BaseModel):
    seq: int
    ts: str
    event: str
    actor: str
    subject_id: str
    data: dict[str, Any]
    hash: str

PurchaseText = Annotated[str, StringConstraints(
    strip_whitespace=True, min_length=1, max_length=2000
)]

class InterpretPaymentBody(_Strict):
    """Untrusted natural-language purchase request."""
    purchase_text: PurchaseText
