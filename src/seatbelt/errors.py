"""Exception types shared across the project."""

from __future__ import annotations

from typing import Any


class SeatbeltError(Exception):
    """Base class for all errors raised by this project."""


class ConfigError(SeatbeltError):
    """Configuration is missing or unsafe."""


class PayPalError(SeatbeltError):
    """PayPal returned an error or could not be reached."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        name: str | None = None,
        debug_id: str | None = None,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.name = name
        self.debug_id = debug_id
        self.details = details or []

    @property
    def issues(self) -> list[str]:
        """Machine-readable issue codes, e.g. ['ORDER_NOT_APPROVED']."""
        return [d["issue"] for d in self.details if "issue" in d]


class PayPalAuthError(PayPalError):
    """Credentials were rejected."""



class MandateError(SeatbeltError):
    """A mandate is invalid, unsafe, or cannot be issued."""


class MalformedMandateError(MandateError):
    """The mandate token is not in the expected format."""


class MandateSignatureError(MandateError):
    """The signature does not match: the mandate was tampered with or signed by another key."""


class MandateExpiredError(MandateError):
    """The mandate's validity window has ended."""


class MandateNotYetValidError(MandateError):
    """The mandate's validity window has not started."""



class AuditIntegrityError(RuntimeError):
    """Audit history or its external checkpoint failed verification."""


class StoreError(SeatbeltError):
    """Base class for storage-layer errors."""


class NotFoundError(StoreError):
    """The requested record does not exist."""


class IdempotencyConflictError(StoreError):
    """The same request_id was reused with different details."""


class InvalidTransitionError(StoreError):
    """The payment is not in a state that allows this action."""


class MandateRevokedError(MandateError):
    """The mandate was revoked and can no longer be used."""



class ExecutionError(SeatbeltError):
    """A payment could not be executed (the money did NOT move)."""