"""A small, hardened PayPal REST client.

- Caches the OAuth token and refreshes it before expiry (or once on a 401).
- Retries transient failures (network errors, 429, 5xx) with exponential backoff.
- Reuses one PayPal-Request-Id across retries so a retried POST can never double-charge.
- Never logs secrets.
"""

from __future__ import annotations

import logging
import random
import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

import httpx
import re

from seatbelt.config import Settings
from seatbelt.errors import PayPalAuthError, PayPalError
from seatbelt.paypal.models import CaptureResult, Money, Order

log = logging.getLogger(__name__)

_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
_TOKEN_EXPIRY_SKEW_SECONDS = 60
_MAX_BACKOFF_SECONDS = 8.0
_SAFE_ORDER_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class PayPalClient:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._sleep = sleep
        self._clock = clock
        self._http = httpx.Client(
            base_url=settings.paypal_base_url,
            timeout=settings.paypal_timeout_seconds,
            transport=transport,
        )
        self._token: str | None = None
        self._token_expires_at: float = 0.0
        self._token_lock = threading.Lock()

    # -- lifecycle ---------------------------------------------------------
    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> PayPalClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- auth --------------------------------------------------------------
    def _get_token(self, *, force_refresh: bool = False) -> str:
        with self._token_lock:
            if (
                not force_refresh
                and self._token
                and self._clock() < self._token_expires_at - _TOKEN_EXPIRY_SKEW_SECONDS
            ):
                return self._token

            try:
                resp = self._http.post(
                    "/v1/oauth2/token",
                    auth=(
                        self._settings.paypal_client_id.get_secret_value(),
                        self._settings.paypal_client_secret.get_secret_value(),
                    ),
                    data={"grant_type": "client_credentials"},
                )
            except httpx.TransportError as exc:
                raise PayPalError(f"Could not reach PayPal for authentication: {exc}") from exc

            if resp.status_code in (400, 401):
                raise PayPalAuthError(
                    "PayPal rejected the client credentials. Check PAYPAL_CLIENT_ID / "
                    "PAYPAL_CLIENT_SECRET and that PAYPAL_ENV matches where they came from.",
                    status_code=resp.status_code,
                )
            if not resp.is_success:
                raise self._to_error(resp)

            body = resp.json()
            self._token = body["access_token"]
            self._token_expires_at = self._clock() + float(body.get("expires_in", 300))
            log.debug("Obtained PayPal access token")
            return self._token

    # -- low-level request -------------------------------------------------
    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        headers: dict[str, str] = {}
        if method.upper() == "POST":
            # One id for ALL attempts of this logical request.
            headers["PayPal-Request-Id"] = request_id or str(uuid.uuid4())
            headers["Content-Type"] = "application/json"

        attempt = 0
        refreshed = False
        while True:
            headers["Authorization"] = f"Bearer {self._get_token()}"
            try:
                resp = self._http.request(method, path, json=json, headers=headers)
            except httpx.TransportError as exc:
                if attempt >= self._settings.paypal_max_retries:
                    raise PayPalError(f"Network error talking to PayPal: {exc}") from exc
                self._backoff(attempt, None)
                attempt += 1
                continue

            if resp.status_code == 401 and not refreshed:
                refreshed = True
                self._get_token(force_refresh=True)
                continue

            if resp.status_code in _RETRYABLE_STATUS and attempt < self._settings.paypal_max_retries:
                log.warning(
                    "PayPal returned %s; retrying (attempt %s)", resp.status_code, attempt + 1
                )
                self._backoff(attempt, resp.headers.get("Retry-After"))
                attempt += 1
                continue

            if resp.is_success:
                return resp.json() if resp.content else {}
            raise self._to_error(resp)

    def _backoff(self, attempt: int, retry_after: str | None) -> None:
        delay = min(0.5 * (2**attempt), _MAX_BACKOFF_SECONDS)
        if retry_after and retry_after.isdigit():
            delay = min(float(retry_after), _MAX_BACKOFF_SECONDS)
        self._sleep(delay + random.uniform(0, 0.25))

    @staticmethod
    def _to_error(resp: httpx.Response) -> PayPalError:
        try:
            body = resp.json()
        except ValueError:
            body = {}
        return PayPalError(
            body.get("message") or f"PayPal request failed with HTTP {resp.status_code}",
            status_code=resp.status_code,
            name=body.get("name"),
            debug_id=body.get("debug_id"),
            details=body.get("details"),
        )

    # -- orders ------------------------------------------------------------
    def create_order(
        self,
        money: Money,
        *,
        description: str,
        reference_id: str,
        request_id: str | None = None,
    ) -> Order:
        body = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "reference_id": reference_id,
                    "description": description[:127],
                    "amount": {
                        "currency_code": money.currency,
                        "value": money.to_paypal_value(),
                    },
                }
            ],
            "payment_source": {
                "paypal": {
                    "experience_context": {
                        "return_url": str(self._settings.paypal_return_url),
                        "cancel_url": str(self._settings.paypal_cancel_url),
                        "user_action": "PAY_NOW",
                    }
                }
            },
        }
        return Order.from_api(
            self._request("POST", "/v2/checkout/orders", json=body, request_id=request_id)
        )

    @staticmethod
    def _validate_order_id(order_id: str) -> None:
        if not _SAFE_ORDER_ID.fullmatch(order_id):
            raise ValueError("Invalid PayPal order ID")

    def get_order(self, order_id: str) ->Order:
        self._validate_order_id(order_id)
        return Order.from_api(
            self._request("GET",f"/v2/checkout/orders/{order_id}")
        )
    def capture_order(
        self,
        order_id: str,
        *,
        request_id: str | None = None,
    ) -> CaptureResult:
        self._validate_order_id(order_id)
        body = self._request(
            "POST",
            f"/v2/checkout/orders/{order_id}/capture",
            request_id=request_id,
        )
        return CaptureResult.from_api(body)