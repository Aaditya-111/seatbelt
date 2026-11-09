"""Typed, validated configuration. Everything comes from environment variables or .env."""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PAYPAL_BASE_URLS: dict[str, str] = {
    "sandbox": "https://api-m.sandbox.paypal.com",
    "live": "https://api-m.paypal.com",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    paypal_client_id: SecretStr
    paypal_client_secret: SecretStr
    paypal_env: Literal["sandbox", "live"] = "sandbox"
    allow_live: bool = False
    paypal_expected_merchant_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
    )

    paypal_webhook_id: str | None = Field(default=None, min_length=1, max_length=128)
    paypal_return_url: AnyHttpUrl
    paypal_cancel_url: AnyHttpUrl

    paypal_timeout_seconds: float = Field(default=20.0, gt=0, le=120)
    paypal_max_retries: int = Field(default=3, ge=0, le=6)

    mandate_signing_key: SecretStr
    mandate_max_ttl_hours: int = Field(default=24, ge=1, le=720)

    admin_api_key: SecretStr
    server_host: str = Field(default="127.0.0.1", min_length=1)
    server_port: int = Field(default=8000, ge=1, le=65535)

    database_path: str = Field(default="seatbelt.db", min_length=1)
    audit_checkpoint_path: str | None = None
    policy_budget_alert_ratio: Decimal = Field(default=Decimal("0.8"), gt=0, le=1)

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_json: bool = False

    @field_validator("paypal_client_id", "paypal_client_secret")
    @classmethod
    def _paypal_credentials_must_be_nonblank(
        cls, v: SecretStr
    ) -> SecretStr:
        value = v.get_secret_value()
        if not value or not value.strip():
            raise ValueError("PayPal credentials cannot be blank")
        if value != value.strip():
            raise ValueError("PayPal credentials cannot contain surrounding whitespace")
        return v

    @field_validator("mandate_signing_key")
    @classmethod
    def _signing_key_is_long_enough(cls, v: SecretStr) -> SecretStr:
        value = v.get_secret_value()
        if len(value) < 32:
            raise ValueError("MANDATE_SIGNING_KEY must be at least 32 characters")
        if not value.strip() or value != value.strip():
            raise ValueError("MANDATE_SIGNING_KEY cannot be blank or whitespace-padded")
        return v

    @field_validator("admin_api_key")
    @classmethod
    def _admin_key_is_long_enough(cls, v: SecretStr) -> SecretStr:
        value = v.get_secret_value()
        if len(value) < 24:
            raise ValueError("ADMIN_API_KEY must be at least 24 characters")
        if not value.strip() or value != value.strip():
            raise ValueError("ADMIN_API_KEY cannot be blank or whitespace-padded")
        return v
    @field_validator("paypal_expected_merchant_id")
    @classmethod
    def _clean_paypal_merchant_id(cls, v: str | None) -> str | None:
        if v is None:
            return None
        value = v.strip()
        if not value:
            raise ValueError("PAYPAL_EXPECTED_MERCHANT_ID cannot be blank")
        return value

    @model_validator(mode="after")
    def _keys_must_differ(self) -> Settings:
        if self.admin_api_key.get_secret_value() == self.mandate_signing_key.get_secret_value():
            raise ValueError("ADMIN_API_KEY and MANDATE_SIGNING_KEY must be different secrets")
        return self

    @model_validator(mode="after")
    def _refuse_live_without_opt_in(self) -> Settings:
        if self.paypal_env != "live":
            return self

        if not self.allow_live:
            raise ValueError(
                "PAYPAL_ENV=live is blocked. Set ALLOW_LIVE=true only if you "
                "really intend to move real money."
            )

        if not self.paypal_expected_merchant_id:
            raise ValueError(
                "PAYPAL_EXPECTED_MERCHANT_ID is required in live mode"
            )

        if not self.paypal_webhook_id:
            raise ValueError(
                "PAYPAL_WEBHOOK_ID is required in live mode"
            )

        if (
            self.paypal_return_url.scheme != "https"
            or self.paypal_cancel_url.scheme != "https"
        ):
            raise ValueError(
                "PayPal live callback URLs must use HTTPS"
            )

        return self


    @property
    def paypal_base_url(self) -> str:
        return PAYPAL_BASE_URLS[self.paypal_env]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load settings once per process. Raises a clear error if config is invalid."""
    return Settings()  # type: ignore[call-arg]
