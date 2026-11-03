"""Issue and verify signed mandates.

Token format:  base64url(payload_json) + "." + base64url(HMAC-SHA256(payload_json))

The signature is checked over the exact bytes received, BEFORE the payload is parsed,
so a tampered token is rejected without ever being interpreted.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from pydantic import SecretStr, ValidationError

from seatbelt.errors import (
    MalformedMandateError,
    MandateError,
    MandateExpiredError,
    MandateNotYetValidError,
    MandateSignatureError,
)
from seatbelt.mandate.models import Mandate

MIN_KEY_LENGTH = 32
CLOCK_SKEW = timedelta(seconds=30)


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


_B64URL = re.compile(r"[A-Za-z0-9_-]+")


def _b64d(text: str) -> bytes:
    # urlsafe_b64decode silently skips illegal characters, so check the alphabet first.
    if not _B64URL.fullmatch(text):
        raise MalformedMandateError("mandate token contains illegal characters")
    try:
        return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except (binascii.Error, ValueError) as exc:
        raise MalformedMandateError("mandate token is not valid base64url") from exc


def _key_bytes(key: SecretStr | str | bytes) -> bytes:
    if isinstance(key, SecretStr):
        key = key.get_secret_value()
    raw = key.encode("utf-8") if isinstance(key, str) else key
    if len(raw) < MIN_KEY_LENGTH:
        raise MandateError(f"signing key must be at least {MIN_KEY_LENGTH} bytes")
    return raw


def _sign(payload: bytes, key: SecretStr | str | bytes) -> bytes:
    return hmac.new(_key_bytes(key), payload, hashlib.sha256).digest()


def encode_mandate(mandate: Mandate, key: SecretStr | str | bytes) -> str:
    """Serialise and sign a mandate into a compact token the agent can carry."""
    payload = json.dumps(
        mandate.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return f"{_b64e(payload)}.{_b64e(_sign(payload, key))}"


def decode_mandate(
    token: str,
    key: SecretStr | str | bytes,
    *,
    now: datetime | None = None,
) -> Mandate:
    """Verify signature and validity window, then return the mandate.

    Raises a MandateError subclass for any problem; never returns an unverified mandate.
    """
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)

    parts = token.split(".") if isinstance(token, str) else []
    if len(parts) != 2 or not all(parts):
        raise MalformedMandateError("mandate token must have the form <payload>.<signature>")

    payload = _b64d(parts[0])
    signature = _b64d(parts[1])

    if not hmac.compare_digest(signature, _sign(payload, key)):
        raise MandateSignatureError("mandate signature is invalid")

    try:
        mandate = Mandate.model_validate(json.loads(payload))
    except (ValueError, ValidationError) as exc:
        raise MalformedMandateError(f"mandate payload is invalid: {exc}") from exc

    if now < mandate.issued_at - CLOCK_SKEW:
        raise MandateNotYetValidError("mandate is not valid yet")
    if now >= mandate.expires_at:
        raise MandateExpiredError("mandate has expired")
    return mandate


def issue_mandate(
    *,
    key: SecretStr | str | bytes,
    agent_id: str,
    currency: str,
    per_payment_limit: str | int | Decimal,
    total_limit: str | int | Decimal,
    approval_threshold: str | int | Decimal,
    allowed_payees: Iterable[str],
    ttl: timedelta,
    max_ttl: timedelta,
    now: datetime | None = None,
) -> tuple[Mandate, str]:
    """Create a mandate and its signed token. Refuses lifetimes longer than max_ttl."""
    if ttl <= timedelta(0):
        raise MandateError("ttl must be positive")
    if ttl > max_ttl:
        raise MandateError(f"ttl {ttl} exceeds the maximum allowed {max_ttl}")

    issued = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    try:
        mandate = Mandate(
            agent_id=agent_id,
            currency=currency,
            per_payment_limit=per_payment_limit,
            total_limit=total_limit,
            approval_threshold=approval_threshold,
            allowed_payees=tuple(allowed_payees),
            issued_at=issued,
            expires_at=issued + ttl,
        )
    except ValidationError as exc:
        raise MandateError(f"invalid mandate: {exc}") from exc
    return mandate, encode_mandate(mandate, key)