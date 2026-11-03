import json

import httpx
import pytest

from seatbelt.errors import PayPalAuthError, PayPalError
from seatbelt.paypal import Money, PayPalClient

TOKEN = {"access_token": "tok-1", "expires_in": 3600}
ORDER = {
    "id": "ORD1",
    "status": "PAYER_ACTION_REQUIRED",
    "links": [{"rel": "payer-action", "href": "https://paypal.test/approve?token=ORD1"}],
}
CAPTURED = {
    "id": "ORD1",
    "status": "COMPLETED",
    "purchase_units": [
        {
            "payments": {
                "captures": [
                    {"id": "CAP1", "amount": {"value": "10.00", "currency_code": "USD"}}
                ]
            }
        }
    ],
}


class Recorder:
    """Scripted fake PayPal. Each route maps to a list of responses served in order."""

    def __init__(self, routes):
        self.routes = {k: list(v) for k, v in routes.items()}
        self.calls: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        key = f"{request.method} {request.url.path}"
        queue = self.routes[key]
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        status, body = item[0], item[1]
        headers = item[2] if len(item) > 2 else {}
        return httpx.Response(status, json=body, headers=headers)


def make_client(settings, routes):
    rec = Recorder(routes)
    sleeps: list[float] = []
    client = PayPalClient(settings, transport=httpx.MockTransport(rec), sleep=sleeps.append)
    return client, rec, sleeps


def test_create_order_parses_approve_url_and_sends_correct_body(settings):
    client, rec, _ = make_client(
        settings,
        {"POST /v1/oauth2/token": [(200, TOKEN)], "POST /v2/checkout/orders": [(201, ORDER)]},
    )
    order = client.create_order(
        Money(amount="10", currency="USD"), description="Test", reference_id="ref-1"
    )
    assert order.id == "ORD1"
    assert order.approve_url.endswith("token=ORD1")

    sent = json.loads(rec.calls[-1].content)
    assert sent["purchase_units"][0]["amount"] == {"currency_code": "USD", "value": "10.00"}
    ctx = sent["payment_source"]["paypal"]["experience_context"]
    assert ctx["return_url"] == "https://app.test/success"
    assert rec.calls[-1].headers["Authorization"] == "Bearer tok-1"


def test_token_is_cached_across_calls(settings):
    client, rec, _ = make_client(
        settings,
        {
            "POST /v1/oauth2/token": [(200, TOKEN)],
            "GET /v2/checkout/orders/ORD1": [(200, ORDER)],
        },
    )
    client.get_order("ORD1")
    client.get_order("ORD1")
    token_calls = [c for c in rec.calls if c.url.path == "/v1/oauth2/token"]
    assert len(token_calls) == 1


def test_expired_token_is_refreshed(settings):
    now = [0.0]
    rec = Recorder(
        {
            "POST /v1/oauth2/token": [
                (200, {"access_token": "a", "expires_in": 100}),
                (200, {"access_token": "b", "expires_in": 100}),
            ],
            "GET /v2/checkout/orders/ORD1": [(200, ORDER)],
        }
    )
    client = PayPalClient(settings, transport=httpx.MockTransport(rec), clock=lambda: now[0])
    client.get_order("ORD1")
    now[0] = 500.0
    client.get_order("ORD1")
    auths = [c.headers["Authorization"] for c in rec.calls if c.url.path.startswith("/v2")]
    assert auths == ["Bearer a", "Bearer b"]


def test_401_triggers_one_token_refresh_then_succeeds(settings):
    client, rec, _ = make_client(
        settings,
        {
            "POST /v1/oauth2/token": [
                (200, {"access_token": "old", "expires_in": 3600}),
                (200, {"access_token": "new", "expires_in": 3600}),
            ],
            "GET /v2/checkout/orders/ORD1": [
                (401, {"name": "AUTHENTICATION_FAILURE"}),
                (200, ORDER),
            ],
        },
    )
    assert client.get_order("ORD1").id == "ORD1"


def test_bad_credentials_raise_auth_error(settings):
    client, _, _ = make_client(
        settings, {"POST /v1/oauth2/token": [(401, {"error": "invalid_client"})]}
    )
    with pytest.raises(PayPalAuthError):
        client.get_order("ORD1")


def test_retries_5xx_with_same_idempotency_key(settings):
    client, rec, sleeps = make_client(
        settings,
        {
            "POST /v1/oauth2/token": [(200, TOKEN)],
            "POST /v2/checkout/orders": [
                (503, {"message": "down"}),
                (503, {"message": "down"}),
                (201, ORDER),
            ],
        },
    )
    order = client.create_order(Money(amount="5", currency="USD"), description="x", reference_id="r")
    assert order.id == "ORD1"
    order_calls = [c for c in rec.calls if c.url.path == "/v2/checkout/orders"]
    assert len(order_calls) == 3
    assert len({c.headers["PayPal-Request-Id"] for c in order_calls}) == 1
    assert len(sleeps) == 2


def test_gives_up_after_max_retries(settings):
    client, rec, _ = make_client(
        settings,
        {
            "POST /v1/oauth2/token": [(200, TOKEN)],
            "POST /v2/checkout/orders": [(503, {"message": "down"})],
        },
    )
    with pytest.raises(PayPalError) as ei:
        client.create_order(Money(amount="5", currency="USD"), description="x", reference_id="r")
    assert ei.value.status_code == 503
    order_calls = [c for c in rec.calls if c.url.path == "/v2/checkout/orders"]
    assert len(order_calls) == settings.paypal_max_retries + 1


def test_retry_after_header_is_honoured(settings):
    client, _, sleeps = make_client(
        settings,
        {
            "POST /v1/oauth2/token": [(200, TOKEN)],
            "GET /v2/checkout/orders/ORD1": [
                (429, {"message": "slow"}, {"Retry-After": "3"}),
                (200, ORDER),
            ],
        },
    )
    client.get_order("ORD1")
    assert 3.0 <= sleeps[0] <= 3.25


def test_business_errors_are_not_retried_and_expose_issue_codes(settings):
    err = {
        "name": "UNPROCESSABLE_ENTITY",
        "message": "failed business validation",
        "debug_id": "dbg123",
        "details": [{"issue": "ORDER_NOT_APPROVED"}],
    }
    client, rec, sleeps = make_client(
        settings,
        {
            "POST /v1/oauth2/token": [(200, TOKEN)],
            "POST /v2/checkout/orders/ORD1/capture": [(422, err)],
        },
    )
    with pytest.raises(PayPalError) as ei:
        client.capture_order("ORD1")
    assert ei.value.status_code == 422
    assert ei.value.debug_id == "dbg123"
    assert ei.value.issues == ["ORDER_NOT_APPROVED"]
    assert sleeps == []


def test_capture_parses_result(settings):
    client, _, _ = make_client(
        settings,
        {
            "POST /v1/oauth2/token": [(200, TOKEN)],
            "POST /v2/checkout/orders/ORD1/capture": [(201, CAPTURED)],
        },
    )
    result = client.capture_order("ORD1")
    assert (result.capture_id, str(result.amount), result.currency) == ("CAP1", "10.00", "USD")


def test_network_errors_are_retried_then_raised(settings):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json=TOKEN)
        calls["n"] += 1
        raise httpx.ConnectError("boom")

    client = PayPalClient(settings, transport=httpx.MockTransport(handler), sleep=lambda s: None)
    with pytest.raises(PayPalError, match="Network error"):
        client.get_order("ORD1")
    assert calls["n"] == settings.paypal_max_retries + 1