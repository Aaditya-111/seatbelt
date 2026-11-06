"""Typed request/response models for the PayPal calls we use."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

ZERO_DECIMAL_CURRENCIES = frozenset({"JPY", "HUF", "TWD"})


class Money(BaseModel):
    model_config = ConfigDict(frozen=True)

    amount: Decimal = Field(gt=Decimal("0"))
    currency: str = Field(pattern=r"^[A-Z]{3}$")

    @field_validator("amount", mode="before")
    @classmethod
    def _no_floats(cls, v: Any) -> Any:
        if isinstance(v, float):
            raise ValueError("amount must be a str, int or Decimal, not float")
        return v

    def to_paypal_value(self) -> str:
        places = (
            Decimal("1")
            if self.currency in ZERO_DECIMAL_CURRENCIES
            else Decimal("0.01")
        )
        quantized = self.amount.quantize(places, rounding=ROUND_HALF_UP)
        if quantized <= 0:
            raise ValueError("amount rounds to zero")
        return format(quantized, "f")


class OrderPurchaseUnit(BaseModel):
    """The PayPal purchase-unit fields required for independent verification."""

    model_config = ConfigDict(frozen=True)

    reference_id: str | None = None
    custom_id: str | None = None
    invoice_id: str | None = None
    amount: Decimal | None = None
    currency_code: str | None = None
    merchant_id: str | None = None
    capture_id: str | None = None
    capture_amount: Decimal | None = None
    capture_currency: str | None = None


class Order(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    status: str
    approve_url: str | None = None
    purchase_units: tuple[OrderPurchaseUnit, ...] = ()

    @classmethod
    def from_api(cls, body: dict[str, Any]) -> Order:
        try:
            links = body.get("links", [])
            approve = next(
                (
                    link["href"]
                    for link in links
                    if link.get("rel") in ("payer-action", "approve")
                    and isinstance(link.get("href"), str)
                ),
                None,
            )

            units = []
            for unit in body.get("purchase_units", []):
                amount = unit.get("amount") or {}
                payee = unit.get("payee") or {}
                payments = unit.get("payments") or {}
                captures = payments.get("captures") or []
                capture = captures[0] if len(captures) == 1 else {}
                capture_amount = capture.get("amount") or {}

                units.append(
                    OrderPurchaseUnit(
                        reference_id=unit.get("reference_id"),
                        custom_id=unit.get("custom_id"),
                        invoice_id=unit.get("invoice_id"),
                        amount=(
                            Decimal(amount["value"])
                            if amount.get("value") is not None
                            else None
                        ),
                        currency_code=amount.get("currency_code"),
                        merchant_id=payee.get("merchant_id"),
                        capture_id=capture.get("id"),
                        capture_amount=(
                            Decimal(capture_amount["value"])
                            if capture_amount.get("value") is not None
                            else None
                        ),
                        capture_currency=capture_amount.get("currency_code"),
                    )
                )

            return cls(
                id=body["id"],
                status=body["status"],
                approve_url=approve,
                purchase_units=tuple(units),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                "Unexpected PayPal order response"
            ) from exc

    def verify_checkout_identity(
        self,
        *,
        expected_order_id: str,
        expected_reference_id: str,
        expected_money: Money,
        expected_merchant_id: str,
    ) -> None:
        """Verify checkout identity and money without assuming its lifecycle state."""
        if not expected_merchant_id or not expected_merchant_id.strip():
            raise ValueError("Expected PayPal merchant ID is not configured")

        if self.id != expected_order_id:
            raise ValueError("PayPal order ID does not match the stored order")

        if len(self.purchase_units) != 1:
            raise ValueError("PayPal order must contain exactly one purchase unit")

        unit = self.purchase_units[0]

        if unit.reference_id != expected_reference_id:
            raise ValueError("PayPal purchase reference does not match the payment")

        if unit.amount is None or unit.currency_code is None:
            raise ValueError("PayPal order is missing its purchase amount")

        if unit.amount != Decimal(expected_money.to_paypal_value()):
            raise ValueError("PayPal order amount does not match the authorized amount")

        if unit.currency_code != expected_money.currency:
            raise ValueError("PayPal order currency does not match the authorized currency")

        if unit.merchant_id != expected_merchant_id:
            raise ValueError("PayPal merchant ID does not match the configured merchant")

    def verify_for_cancellation(
        self,
        *,
        expected_order_id: str,
        expected_reference_id: str,
        expected_money: Money,
        expected_merchant_id: str,
    ) -> None:
        """Verify that PayPal confirms the order is voided before releasing funds."""
        self.verify_checkout_identity(
            expected_order_id=expected_order_id,
            expected_reference_id=expected_reference_id,
            expected_money=expected_money,
            expected_merchant_id=expected_merchant_id,
        )

        if self.status != "VOIDED":
            raise ValueError("PayPal order is not in a terminal cancelled state")

    def verify_for_capture(
        self,
        *,
        expected_order_id: str,
        expected_reference_id: str,
        expected_money: Money,
        expected_merchant_id: str,
    ) -> None:
        """Reject any PayPal order that does not exactly match Seatbelt's record."""

        if not expected_merchant_id or not expected_merchant_id.strip():
            raise ValueError("Expected PayPal merchant ID is not configured")

        if self.id != expected_order_id:
            raise ValueError("PayPal order ID does not match the stored order")

        if self.status not in {"APPROVED", "COMPLETED"}:
            raise ValueError("PayPal order has not been approved by the payer")

        if len(self.purchase_units) != 1:
            raise ValueError("PayPal order must contain exactly one purchase unit")

        unit = self.purchase_units[0]

        if unit.reference_id != expected_reference_id:
            raise ValueError("PayPal purchase reference does not match the payment")

        if unit.amount is None or unit.currency_code is None:
            raise ValueError("PayPal order is missing its purchase amount")

        expected_amount = Decimal(expected_money.to_paypal_value())

        if unit.amount != expected_amount:
            raise ValueError("PayPal order amount does not match the authorized amount")

        if unit.currency_code != expected_money.currency:
            raise ValueError("PayPal order currency does not match the authorized currency")

        if unit.merchant_id != expected_merchant_id:
            raise ValueError("PayPal merchant ID does not match the configured merchant")


class CaptureResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    order_id: str
    status: str
    capture_id: str
    amount: Decimal
    currency: str

    @classmethod
    def from_api(cls, body: dict[str, Any]) -> CaptureResult:
        try:
            units = body["purchase_units"]
            if len(units) != 1:
                raise ValueError("Expected exactly one purchase unit")

            captures = units[0]["payments"]["captures"]
            if len(captures) != 1:
                raise ValueError("Expected exactly one capture")

            capture = captures[0]
            return cls(
                order_id=body["id"],
                status=body["status"],
                capture_id=capture["id"],
                amount=Decimal(capture["amount"]["value"]),
                currency=capture["amount"]["currency_code"],
            )
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ValueError(
                "Unexpected PayPal capture response"
            ) from exc
