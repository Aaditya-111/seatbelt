"""The Mandate: a signed, time-limited spending permission for one agent."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _reject_float(v: Any) -> Any:
    if isinstance(v, float):
        raise ValueError("money values must be str, int or Decimal, not float")
    return v


class Mandate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    mandate_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    agent_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.:-]+$")
    currency: str = Field(pattern=r"^[A-Z]{3}$")

    per_payment_limit: Decimal = Field(gt=Decimal("0"))
    total_limit: Decimal = Field(gt=Decimal("0"))
    # Payments above this amount need a human to approve them. 0 means "always ask".
    approval_threshold: Decimal = Field(ge=Decimal("0"))

    # Exact payee identifiers the agent may pay (e.g. merchant ids). No wildcards.
    allowed_payees: tuple[str, ...] = Field(min_length=1, max_length=100)

    issued_at: datetime
    expires_at: datetime

    @field_validator("per_payment_limit", "total_limit", "approval_threshold", mode="before")
    @classmethod
    def _no_floats(cls, v: Any) -> Any:
        return _reject_float(v)

    @field_validator("issued_at", "expires_at")
    @classmethod
    def _utc_only(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("datetimes must be timezone-aware")
        return v.astimezone(timezone.utc)

    @field_validator("allowed_payees", mode="before")
    @classmethod
    def _normalise_payees(cls, v: Any) -> Any:
        if isinstance(v, str) or not hasattr(v, "__iter__"):
            raise ValueError("allowed_payees must be a list of strings")
        cleaned: set[str] = set()
        for item in v:
            if not isinstance(item, str):
                raise ValueError("allowed_payees must contain only strings")
            item = item.strip().lower()
            if not item or len(item) > 128:
                raise ValueError("payee ids must be 1-128 characters")
            if "*" in item:
                raise ValueError("wildcards are not allowed in allowed_payees")
            cleaned.add(item)
        return tuple(sorted(cleaned))

    @model_validator(mode="after")
    def _limits_are_consistent(self) -> Mandate:
        if self.expires_at <= self.issued_at:
            raise ValueError("expires_at must be after issued_at")
        if self.per_payment_limit > self.total_limit:
            raise ValueError("per_payment_limit cannot exceed total_limit")
        if self.approval_threshold > self.per_payment_limit:
            raise ValueError("approval_threshold cannot exceed per_payment_limit")
        return self