"""Records the store hands back."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict

from seatbelt.mandate.models import Mandate
from seatbelt.policy.models import Reason, Verdict



class PaymentStatus(str, Enum):
    DENIED = "denied"  # blocked by policy; nothing reserved
    PENDING_APPROVAL = "pending_approval"  # waiting for a human; budget is held
    RESERVED = "reserved"  # cleared for payment execution; budget is held
    AWAITING_PAYER = "awaiting_payer"  # PayPal order created; buyer approval pending
    CAPTURED = "captured"  # money moved
    REJECTED = "rejected"  # a human said no; budget released
    FAILED = "failed"  # payment definitively failed; budget released
    CANCELLED = "cancelled"  # mandate revoked/expired or checkout cancelled


# Statuses whose amount counts against the mandate's budget.

HOLDING_STATUSES = (
    PaymentStatus.PENDING_APPROVAL,
    PaymentStatus.RESERVED,
    PaymentStatus.AWAITING_PAYER,
    PaymentStatus.CAPTURED,
)



class PaymentRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    payment_id: str
    mandate_id: str
    request_id: str
    agent_id: str
    payee: str
    amount: Decimal
    currency: str
    description: str
    status: PaymentStatus
    verdict: Verdict
    reasons: tuple[Reason, ...]
    paypal_order_id: str | None = None
    paypal_approve_url: str | None = None
    paypal_capture_id: str | None = None
    decided_by: str | None = None
    failure: str | None = None
    created_at: datetime
    updated_at: datetime


class StoredMandate(BaseModel):
    model_config = ConfigDict(frozen=True)

    mandate: Mandate
    committed: Decimal
    created_at: datetime
    revoked_at: datetime | None = None


class ChainStatus(BaseModel):
    ok: bool
    entries: int
    first_bad_seq: int | None = None
    reason: str | None = None
    head_seq: int | None = None
    head_hash: str | None = None