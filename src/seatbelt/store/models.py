
"""Records the store hands back."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from seatbelt.mandate.models import Mandate
from seatbelt.policy.models import Reason, Verdict


class ChainStatus(BaseModel):
    """Result of verifying the tamper-evident audit chain."""

    model_config = ConfigDict(frozen=True)

    ok: bool
    entries: int
    first_bad_seq: int | None = None
    reasons: tuple[Reason, ...] = Field(default_factory=tuple)
    head_seq: int | None = None
    head_hash: str | None = None
    checkpoint_ok: bool | None = None
    checkpoint_seq: int | None = None
    checkpoint_error: str | None = None


class PaymentStatus(str, Enum):
    DENIED = "denied"
    PENDING_APPROVAL = "pending_approval"
    RESERVED = "reserved"
    AWAITING_PAYER = "awaiting_payer"
    CAPTURED = "captured"
    REJECTED = "rejected"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PaymentChannel(str, Enum):
    EXECUTOR = "executor"
    PAYPAL = "paypal"


HOLDING_STATUSES = (
    PaymentStatus.PENDING_APPROVAL,
    PaymentStatus.RESERVED,
    PaymentStatus.AWAITING_PAYER,
    PaymentStatus.CAPTURED,
)


class StoredMandate(BaseModel):
    """Mandate together with its current budget and registration state."""

    model_config = ConfigDict(frozen=True)

    mandate: Mandate
    committed: Decimal
    created_at: datetime
    revoked_at: datetime | None = None


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
    reasons: tuple[Reason, ...] = Field(default_factory=tuple)

    payment_channel: PaymentChannel = PaymentChannel.EXECUTOR

    paypal_order_id: str | None = None
    paypal_approve_url: str | None = None
    paypal_capture_id: str | None = None

    decided_by: str | None = None
    failure: str | None = None

    created_at: datetime
    updated_at: datetime
