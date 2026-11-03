"""Typed request/response models for the PayPal calls we use."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# PayPal does not accept decimal places for these currencies.
ZERO_DECIMAL_CURRENCIES = frozenset({"JPY", "HUF", "TWD"})


class Money(BaseModel):
    model_config = ConfigDict(frozen=True)

    amount: Decimal = Field(gt=Decimal("0"))
    currency: str = Field(pattern=r"^[A-Z]{3}$")

    @field_validator("amount", mode="before")
    @classmethod
    def _no_floats(cls, v: Any) -> Any:
        # Floats cause rounding surprises with money; require str/int/Decimal.
        if isinstance(v, float):
            raise ValueError("amount must be a str, int or Decimal, not float")
        return v

    def to_paypal_value(self) -> str:
        places = Decimal("1") if self.currency in ZERO_DECIMAL_CURRENCIES else Decimal("0.01")
        quantized = self.amount.quantize(places, rounding=ROUND_HALF_UP)
        if quantized <= 0:
            raise ValueError("amount rounds to zero")
        return format(quantized, "f")


class Order(BaseModel):
    id: str
    status: str
    approve_url: str | None = None

    @classmethod
    def from_api(cls, body: dict[str, Any]) -> Order:
        links = body.get("links", [])
        approve = next(
            (link["href"] for link in links if link.get("rel") in ("payer-action", "approve")),
            None,
        )
        return cls(id=body["id"], status=body["status"], approve_url=approve)


class CaptureResult(BaseModel):
    order_id: str
    status: str
    capture_id: str
    amount: Decimal
    currency: str

    @classmethod
    def from_api(cls, body: dict[str, Any]) -> CaptureResult:
        try:
            capture = body["purchase_units"][0]["payments"]["captures"][0]
            return cls(
                order_id=body["id"],
                status=body["status"],
                capture_id=capture["id"],
                amount=Decimal(capture["amount"]["value"]),
                currency=capture["amount"]["currency_code"],
            )
        except (KeyError, IndexError) as exc:
            raise ValueError(f"Unexpected capture response shape: missing {exc}") from exc