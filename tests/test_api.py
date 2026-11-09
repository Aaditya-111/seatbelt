import json
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from seatbelt.service import ExecutionResult, FakeExecutor, GuardService, create_app
from seatbelt.store import Database, GuardStore
from seatbelt.paypal.models import CaptureResult, Order, OrderPurchaseUnit

SIGNING_KEY = "k" * 40
ADMIN_KEY = "a" * 30
START = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self):
        self.now = START

    def __call__(self):
        return self.now


class ExplodingExecutor:
    def execute(self, payment):
        raise RuntimeError("super secret internal detail")


def make_client(tmp_path, executor=None, raise_exceptions=True, paypal=None):
    db = Database(tmp_path / "api.db")
    db.initialize()
    clock = Clock()
    service = GuardService(
        GuardStore(db, SIGNING_KEY),
        executor or FakeExecutor(),
        SIGNING_KEY,
        max_mandate_ttl=timedelta(hours=24),
        clock=clock,
        paypal_client=paypal,
        paypal_expected_merchant_id="MERCHANT-1" if paypal is not None else None,
    )
    app = create_app(service, SecretStr(ADMIN_KEY))
    client = TestClient(app, raise_server_exceptions=raise_exceptions)
    client.clock = clock
    client.executor = service._executor
    client.paypal = paypal
    client.store = service._store
    return client


@pytest.fixture
def client(tmp_path):
    return make_client(tmp_path)


ADMIN = {"Authorization": f"Bearer {ADMIN_KEY}"}


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


MANDATE_BODY = dict(
    agent_id="agent-1",
    currency="USD",
    per_payment_limit="100",
    total_limit="300",
    approval_threshold="40",
    allowed_payees=["shop-a", "shop-b"],
    ttl_minutes=60,
)


def issue(client, **overrides):
    r = client.post("/v1/mandates", headers=ADMIN, json={**MANDATE_BODY, **overrides})
    assert r.status_code == 200, r.text
    return r.json()["mandate"], r.json()["token"]


def pay(client, token, **overrides):
    body = dict(request_id="r1", payee="shop-a", amount="20.00", currency="USD")
    body.update(overrides)
    return client.post("/v1/payments", headers=bearer(token), json=body)

def corrupt_latest_audit_hash(client):
    with client.store._db.transaction(write=True) as conn:
        conn.execute(
            """
            UPDATE audit_log
            SET hash = ?
            WHERE seq = (SELECT MAX(seq) FROM audit_log)
            """,
            ("0" * 64,),
        )


def rollback_latest_audit_entry(client):
    with client.store._db.transaction(write=True) as conn:
        conn.execute(
            """
            DELETE FROM audit_log
            WHERE seq = (SELECT MAX(seq) FROM audit_log)
            """
        )


def make_checkpointed_client(tmp_path, paypal):
    checkpoint = tmp_path / "audit-checkpoint.json"
    db = Database(tmp_path / "checkpoint-api.db")
    db.initialize()
    clock = Clock()
    store = GuardStore(
        db,
        SIGNING_KEY,
        audit_checkpoint_path=str(checkpoint),
    )
    service = GuardService(
        store,
        FakeExecutor(),
        SIGNING_KEY,
        max_mandate_ttl=timedelta(hours=24),
        clock=clock,
        paypal_client=paypal,
        paypal_expected_merchant_id="MERCHANT-1",
    )
    app = create_app(service, SecretStr(ADMIN_KEY))
    client = TestClient(app, raise_server_exceptions=False)
    client.clock = clock
    client.executor = service._executor
    client.paypal = paypal
    client.store = store

    # Bootstrap a trusted genesis checkpoint before the first audit write.
    store.create_audit_checkpoint()

    return client, checkpoint


# ---------------- basics ----------------
def test_health_needs_no_credentials(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_openapi_document_lists_the_endpoints(client):
    paths = client.get("/openapi.json").json()["paths"]
    for p in ("/v1/mandates", "/v1/payments", "/v1/payments/{payment_id}/approve", "/v1/audit"):
        assert p in paths


# ---------------- who may call what ----------------
@pytest.mark.parametrize(
    "method, path",
    [
        ("post", "/v1/mandates"),
        ("get", "/v1/mandates/x"),
        ("post", "/v1/mandates/x/revoke"),
        ("get", "/v1/payments"),
        ("post", "/v1/payments/x/approve"),
        ("post", "/v1/payments/x/reject"),
        ("post", "/v1/payments/x/retry"),
        ("get", "/v1/audit"),
        ("get", "/v1/audit/verify"),
        ("post", "/v1/audit/checkpoint"),
    ],
)
def test_admin_endpoints_reject_missing_wrong_and_agent_credentials(client, method, path):
    _, agent_token = issue(client)
    body = {"json": {}} if method == "post" else {}
    for headers in ({}, bearer("wrong-key-" + "x" * 30), bearer(agent_token)):
        r = getattr(client, method)(path, headers=headers, **body)
        assert r.status_code == 401, (path, headers, r.status_code)
        assert r.headers.get("www-authenticate") == "Bearer"


def test_the_admin_key_is_not_accepted_as_an_agent_token(client):
    r = pay(client, ADMIN_KEY)
    assert r.status_code == 401


def test_submitting_a_payment_requires_a_token(client):
    r = client.post(
        "/v1/payments", json=dict(request_id="r", payee="s", amount="1", currency="USD")
    )
    assert r.status_code == 401


# ---------------- issuing mandates ----------------
def test_issue_mandate_returns_a_usable_token(client):
    mandate, token = issue(client)
    assert mandate["agent_id"] == "agent-1" and "." in token
    assert (
        client.get(f"/v1/mandates/{mandate['mandate_id']}", headers=ADMIN).json()["committed"]
        == "0"
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"per_payment_limit": 100},  # JSON number, not string
        {"total_limit": 300.5},
        {"currency": "usd"},
        {"agent_id": "bad agent!"},
        {"allowed_payees": []},
        {"ttl_minutes": 0},
        {"ttl_minutes": 60 * 24 * 31},
        {"surprise_field": "x"},
        {"per_payment_limit": "-5"},
    ],
)
def test_invalid_mandate_requests_are_rejected(client, overrides):
    r = client.post("/v1/mandates", headers=ADMIN, json={**MANDATE_BODY, **overrides})
    assert r.status_code == 422


def test_ttl_beyond_the_server_maximum_is_refused(client):
    r = client.post("/v1/mandates", headers=ADMIN, json={**MANDATE_BODY, "ttl_minutes": 60 * 25})
    assert r.status_code == 422


def test_inconsistent_limits_are_refused(client):
    r = client.post(
        "/v1/mandates",
        headers=ADMIN,
        json={**MANDATE_BODY, "per_payment_limit": "900", "total_limit": "300"},
    )
    assert r.status_code == 422


# ---------------- the payment flow ----------------
def test_small_payment_is_allowed_and_executed(client):
    _, token = issue(client)
    r = pay(client, token)
    body = r.json()
    assert r.status_code == 200
    assert body["status"] == "captured" and body["verdict"] == "allow"
    assert body["amount"] == "20.00"  # a string, never a float
    assert len(client.executor.executed) == 1

def test_corrupted_audit_blocks_payment_api(tmp_path):
    client = make_client(tmp_path, raise_exceptions=False)
    _, token = issue(client)

    corrupt_latest_audit_hash(client)

    response = pay(
        client,
        token,
        request_id="audit-corruption-api-test",
    )

    assert response.status_code == 503
    assert response.json() == {
    "detail": "Payment operations are temporarily disabled due to an integrity check failure."
    }
    assert client.executor.executed == []

    audit = client.store.verify_audit()
    assert audit.ok is False


def test_large_payment_waits_then_admin_approval_executes_it(client):
    _, token = issue(client)
    held = pay(client, token, amount="75.00").json()
    assert held["status"] == "pending_approval" and client.executor.executed == []

    r = client.post(
        f"/v1/payments/{held['payment_id']}/approve", headers=ADMIN, json={"approver": "boss"}
    )
    assert r.status_code == 200 and r.json()["status"] == "captured"
    assert r.json()["decided_by"] == "boss" and len(client.executor.executed) == 1


def test_an_agent_cannot_approve_its_own_payment(client):
    _, token = issue(client)
    held = pay(client, token, amount="75.00").json()
    r = client.post(
        f"/v1/payments/{held['payment_id']}/approve",
        headers=bearer(token),
        json={"approver": "agent-1"},
    )
    assert r.status_code == 401
    assert (
        client.get(f"/v1/payments/{held['payment_id']}", headers=ADMIN).json()["status"]
        == "pending_approval"
    )


def test_rejecting_a_payment(client):
    _, token = issue(client)
    held = pay(client, token, amount="75.00").json()
    r = client.post(
        f"/v1/payments/{held['payment_id']}/reject",
        headers=ADMIN,
        json={"approver": "boss", "reason": "not needed"},
    )
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert client.executor.executed == []


def test_denied_payment_returns_the_reasons(client):
    _, token = issue(client)
    body = pay(client, token, payee="evil-shop").json()
    assert body["status"] == "denied" and body["verdict"] == "deny"
    assert any(r["code"] == "payee_not_allowed" for r in body["reasons"])
    assert client.executor.executed == []


def test_replaying_a_request_returns_the_same_payment_without_paying_again(client):
    _, token = issue(client)
    a = pay(client, token, request_id="dup").json()
    b = pay(client, token, request_id="dup").json()
    assert a["payment_id"] == b["payment_id"] and len(client.executor.executed) == 1


def test_reusing_a_request_id_with_different_details_is_a_409(client):
    _, token = issue(client)
    pay(client, token, request_id="dup", amount="20.00")
    assert pay(client, token, request_id="dup", amount="21.00").status_code == 409


def test_approving_twice_is_a_409(client):
    _, token = issue(client)
    held = pay(client, token, amount="75.00").json()
    url = f"/v1/payments/{held['payment_id']}/approve"
    assert client.post(url, headers=ADMIN, json={"approver": "boss"}).status_code == 200
    assert client.post(url, headers=ADMIN, json={"approver": "boss"}).status_code == 409


def test_unknown_payment_is_a_404(client):
    assert client.get("/v1/payments/nope", headers=ADMIN).status_code == 404


@pytest.mark.parametrize(
    "overrides",
    [
        {"amount": 20},  # number, not string
        {"amount": "20.5.5"},
        {"amount": "0.001"},  # rounds to zero at PayPal
        {"currency": "dollars"},
        {"request_id": "has spaces"},
        {"description": "x" * 501},
        {"agent_id": "someone-else"},  # not a field: identity comes from the token
    ],
)
def test_invalid_payment_requests_are_rejected(client, overrides):
    _, token = issue(client)
    assert pay(client, token, **overrides).status_code == 422


def test_executor_failure_is_reported_as_a_failed_payment(tmp_path):
    client = make_client(tmp_path, FakeExecutor(fail_for_payees={"shop-b"}))
    _, token = issue(client)
    body = pay(client, token, payee="shop-b").json()
    assert body["status"] == "failed"


# ---------------- reading payments ----------------
def test_agent_reads_only_its_own_payments(client):
    _, token_1 = issue(client, agent_id="agent-1")
    _, token_2 = issue(client, agent_id="agent-2")
    mine = pay(client, token_1).json()
    theirs = pay(client, token_2, request_id="other").json()

    assert (
        client.get(f"/v1/payments/{mine['payment_id']}", headers=bearer(token_1)).status_code
        == 200
    )
    assert (
        client.get(f"/v1/payments/{theirs['payment_id']}", headers=bearer(token_1)).status_code
        == 404
    )
    assert client.get(f"/v1/payments/{theirs['payment_id']}", headers=ADMIN).status_code == 200


def test_payment_list_filters_and_bounds(client):
    _, token = issue(client)
    pay(client, token, request_id="a")
    pay(client, token, request_id="b", payee="evil")
    assert len(client.get("/v1/payments", headers=ADMIN).json()) == 2
    denied = client.get("/v1/payments?status=denied", headers=ADMIN).json()
    assert [p["payee"] for p in denied] == ["evil"]
    assert client.get("/v1/payments?limit=0", headers=ADMIN).status_code == 422
    assert client.get("/v1/payments?limit=501", headers=ADMIN).status_code == 422
    assert client.get("/v1/payments?status=bogus", headers=ADMIN).status_code == 422


# ---------------- token problems ----------------
def test_tampered_token_is_a_401(client):
    _, token = issue(client)
    payload, sig = token.split(".")
    bad = f"{payload}.{'A' if sig[0] != 'A' else 'B'}{sig[1:]}"
    assert pay(client, bad).status_code == 401


def test_expired_token_is_a_401(client):
    _, token = issue(client, ttl_minutes=10)
    client.clock.now += timedelta(minutes=11)
    assert pay(client, token).status_code == 401


def test_revoked_mandate_is_a_403_and_cancels_pending_payments(client):
    mandate, token = issue(client)
    held = pay(client, token, amount="75.00").json()
    r = client.post(f"/v1/mandates/{mandate['mandate_id']}/revoke", headers=ADMIN)
    assert r.status_code == 200 and r.json()["payments_cancelled"] == 1
    assert pay(client, token, request_id="after").status_code == 403
    assert (
        client.get(f"/v1/payments/{held['payment_id']}", headers=ADMIN).json()["status"]
        == "cancelled"
    )


# ---------------- retry ----------------
class FailFirstThenWork:
    def __init__(self):
        self.calls = 0

    def execute(self, payment):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("boom")
        return ExecutionResult(capture_id="CAP-OK", order_id="ORD-OK")


def test_stuck_payment_can_be_retried_by_the_admin(tmp_path):
    client = make_client(tmp_path, FailFirstThenWork(), raise_exceptions=False)
    _, token = issue(client)
    assert pay(client, token).status_code == 500
    stuck = client.get("/v1/payments", headers=ADMIN).json()[0]
    assert stuck["status"] == "reserved"
    r = client.post(f"/v1/payments/{stuck['payment_id']}/retry", headers=ADMIN)
    assert r.status_code == 200 and r.json()["status"] == "captured"


# ---------------- error hygiene ----------------
def test_unexpected_errors_return_a_generic_500_without_internals(tmp_path):
    client = make_client(tmp_path, ExplodingExecutor(), raise_exceptions=False)
    _, token = issue(client)
    r = pay(client, token)
    assert r.status_code == 500
    assert r.json() == {"detail": "internal server error"}
    assert "secret" not in r.text


# ---------------- audit ----------------
def test_audit_log_lists_events_and_verifies(client):
    _, token = issue(client)
    pay(client, token)
    events = [e["event"] for e in client.get("/v1/audit", headers=ADMIN).json()]
    assert "payment.captured" in events and "mandate.registered" in events
    status = client.get("/v1/audit/verify", headers=ADMIN).json()
    assert status["ok"] is True and status["head_hash"] and status["entries"] >= 4

def test_checkpoint_endpoint_requires_configured_path(client):
    response = client.post("/v1/audit/checkpoint", headers=ADMIN)

    assert response.status_code == 503
    assert response.json() == {
        "detail": "AUDIT_CHECKPOINT_PATH is not configured"
    }
# ---------------- PayPal API security boundaries ----------------


# ---------------- audit ----------------

def test_checkpoint_rollback_blocks_paypal_checkout_api(tmp_path):
    paypal = APIFakePayPal()
    client, checkpoint = make_checkpointed_client(tmp_path, paypal)
    _, token = issue(client)

    client.store.create_audit_checkpoint()
    assert checkpoint.exists()

    rollback_latest_audit_entry(client)

    response = submit_paypal_api(
        client,
        token,
        request_id="checkpoint-rollback-checkout",
    )

    assert response.status_code == 503, response.text
    assert response.json() == {
        "detail": "Payment operations are temporarily disabled due to an integrity check failure."
    }
    assert paypal.created == []
    assert paypal.captured == []
    status = client.store.verify_audit()
    assert status.ok is False
    assert status.checkpoint_ok is False


def test_checkpoint_rollback_blocks_paypal_capture_api(tmp_path):
    paypal = APIFakePayPal()
    client, checkpoint = make_checkpointed_client(tmp_path, paypal)
    _, token = issue(client)

    checkout = submit_paypal_api(client, token)
    assert checkout.status_code == 200, checkout.text
    assert len(paypal.created) == 1

    client.store.create_audit_checkpoint()
    assert checkpoint.exists()

    rollback_latest_audit_entry(client)

    response = client.get(
        "/v1/paypal/return",
        params={"token": paypal.order_id},
    )

    assert response.status_code == 503, response.text
    assert response.json() == {
        "detail": "Payment operations are temporarily disabled due to an integrity check failure."
    }
    assert paypal.captured == []
    status = client.store.verify_audit()
    assert status.ok is False
    assert status.checkpoint_ok is False


def test_paypal_checkout_requires_agent_authentication(client):
    r = client.post(
        "/v1/paypal/payments",
        json={
            "request_id": "paypal-1",
            "payee": "shop-a",
            "amount": "20.00",
            "currency": "USD",
        },
    )
    assert r.status_code == 401


def test_agent_cannot_select_paypal_channel_on_regular_payment_endpoint(client):
    _, token = issue(client)

    r = pay(
        client,
        token,
        payment_channel="paypal",
    )

    assert r.status_code == 422


def test_paypal_return_rejects_unknown_order_even_with_supplied_payment_id(client):
    r = client.get(
        "/v1/paypal/return",
        params={
            "token": "UNKNOWN-ORDER",
            "payment_id": "some-other-payment",
        },
    )

    assert r.status_code == 404


def test_openapi_document_lists_paypal_endpoints(client):
    paths = client.get("/openapi.json").json()["paths"]

    assert "/v1/paypal/payments" in paths
    assert "/v1/paypal/return" in paths
    assert "/v1/paypal/cancel" in paths
    assert "/v1/paypal/webhook" in paths


# ---------------- PayPal API lifecycle ----------------

class APIFakePayPal:
    def __init__(self, merchant_id="MERCHANT-1"):
        self.merchant_id = merchant_id
        self.order_id = "ORDER-API-1"
        self.capture_id = "CAPTURE-API-1"
        self.reference_id = None
        self.amount = None
        self.currency = None
        self.created = []
        self.captured = []
        self.completed = False
        self.order_status = "APPROVED"
        self.lose_capture_response = False
        self.webhook_signature_valid = True
        self.webhook_verifications = []

    def verify_webhook_signature(self, headers, event, raw_event_body):
        self.webhook_verifications.append((headers, event, raw_event_body))
        return self.webhook_signature_valid

    def create_order(self, money, *, description, reference_id, request_id=None):
        self.reference_id = reference_id
        self.amount = Decimal(money.to_paypal_value())
        self.currency = money.currency
        self.created.append(request_id)

        return Order(
            id=self.order_id,
            status="PAYER_ACTION_REQUIRED",
            approve_url=(
                "https://www.sandbox.paypal.com/"
                "checkoutnow?token=ORDER-API-1"
            ),
            purchase_units=(
                OrderPurchaseUnit(
                    reference_id=reference_id,
                    amount=self.amount,
                    currency_code=self.currency,
                    merchant_id=self.merchant_id,
                ),
            ),
        )

    def get_order(self, order_id):
        assert order_id == self.order_id

        return Order(
            id=self.order_id,
            status="COMPLETED" if self.completed else self.order_status,
            purchase_units=(
                OrderPurchaseUnit(
                    reference_id=self.reference_id,
                    amount=self.amount,
                    currency_code=self.currency,
                    merchant_id=self.merchant_id,
                    capture_id=self.capture_id if self.completed else None,
                    capture_amount=self.amount if self.completed else None,
                    capture_currency=self.currency if self.completed else None,
                ),
            ),
        )

    def capture_order(self, order_id, *, request_id=None):
        assert order_id == self.order_id
        self.captured.append(request_id)
        self.completed = True

        if self.lose_capture_response:
            self.lose_capture_response = False
            raise RuntimeError("simulated lost PayPal capture response")

        return CaptureResult(
            order_id=self.order_id,
            status="COMPLETED",
            capture_id=self.capture_id,
            amount=self.amount,
            currency=self.currency,
        )


def submit_paypal_api(client, token, request_id="api-paypal-1"):
    return client.post(
        "/v1/paypal/payments",
        headers=bearer(token),
        json={
            "request_id": request_id,
            "payee": "shop-a",
            "amount": "20.00",
            "currency": "USD",
            "description": "API lifecycle test",
        },
    )


def test_paypal_api_creates_authenticated_checkout_and_persists_order(tmp_path):
    paypal = APIFakePayPal()
    client = make_client(tmp_path, paypal=paypal)
    _, token = issue(client)

    response = submit_paypal_api(client, token)

    assert response.status_code == 200, response.text
    body = response.json()

    assert body["status"] == "awaiting_payer"
    assert body["payment_channel"] == "paypal"
    assert body["paypal_order_id"] == paypal.order_id
    assert body["paypal_approve_url"].startswith(
        "https://www.sandbox.paypal.com/checkoutnow"
    )
    assert len(paypal.created) == 1
    assert paypal.created[0]


def test_paypal_api_return_verifies_and_captures_order(tmp_path):
    paypal = APIFakePayPal()
    client = make_client(tmp_path, paypal=paypal)
    _, token = issue(client)

    checkout = submit_paypal_api(client, token)
    assert checkout.status_code == 200, checkout.text

    response = client.get(
        "/v1/paypal/return",
        params={"token": paypal.order_id},
    )

    assert response.status_code == 200, response.text
    body = response.json()

    assert body["status"] == "captured"
    assert body["paypal_capture_id"] == paypal.capture_id
    assert len(paypal.captured) == 1
    assert paypal.captured[0]


def test_duplicate_paypal_api_returns_do_not_capture_twice(tmp_path):
    paypal = APIFakePayPal()
    client = make_client(tmp_path, paypal=paypal)
    _, token = issue(client)

    checkout = submit_paypal_api(client, token)
    assert checkout.status_code == 200, checkout.text

    first = client.get(
        "/v1/paypal/return",
        params={"token": paypal.order_id},
    )
    second = client.get(
        "/v1/paypal/return",
        params={"token": paypal.order_id},
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["status"] == "captured"
    assert second.json()["status"] == "captured"
    assert len(paypal.captured) == 1


def test_paypal_api_recovers_lost_capture_response_without_recapturing(tmp_path):
    paypal = APIFakePayPal()
    paypal.lose_capture_response = True
    client = make_client(tmp_path, paypal=paypal, raise_exceptions=False)
    _, token = issue(client)

    checkout = submit_paypal_api(client, token)
    assert checkout.status_code == 200, checkout.text

    first = client.get(
        "/v1/paypal/return",
        params={"token": paypal.order_id},
    )
    assert first.status_code == 500, first.text
    assert len(paypal.captured) == 1

    retry = client.get(
        "/v1/paypal/return",
        params={"token": paypal.order_id},
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["status"] == "captured"
    assert retry.json()["paypal_capture_id"] == paypal.capture_id
    assert len(paypal.captured) == 1


def _paypal_webhook_headers():
    return {
        "PAYPAL-AUTH-ALGO": "SHA256withRSA",
        "PAYPAL-CERT-URL": "https://api.sandbox.paypal.com/cert",
        "PAYPAL-TRANSMISSION-ID": "transmission-test-1",
        "PAYPAL-TRANSMISSION-SIG": "test-signature",
        "PAYPAL-TRANSMISSION-TIME": "2026-11-08T10:00:00Z",
    }


def _completed_capture_event(paypal, event_id="WH-API-CAPTURE-1"):
    return {
        "id": event_id,
        "event_type": "PAYMENT.CAPTURE.COMPLETED",
        "resource": {
            "id": paypal.capture_id,
            "status": "COMPLETED",
            "amount": {
                "value": "20.00",
                "currency_code": "USD",
            },
            "supplementary_data": {
                "related_ids": {
                    "order_id": paypal.order_id,
                },
            },
        },
    }


def test_paypal_webhook_preserves_original_event_body_bytes(tmp_path):
    paypal = APIFakePayPal()
    client = make_client(tmp_path, paypal=paypal)
    _, token = issue(client)

    checkout = submit_paypal_api(client, token, request_id="raw-body-payment")
    assert checkout.status_code == 200, checkout.text

    paypal.completed = True
    event = _completed_capture_event(
        paypal, event_id="WH-RAW-BODY-1"
    )
    raw_body = json.dumps(event, indent=4, ensure_ascii=False).encode("utf-8")

    response = client.post(
        "/v1/paypal/webhook",
        headers={
            **_paypal_webhook_headers(),
            "content-type": "application/json",
        },
        content=raw_body,
    )

    assert response.status_code == 200, response.text
    assert len(paypal.webhook_verifications) == 1
    assert paypal.webhook_verifications[0][2] == raw_body


def test_paypal_webhook_reconciles_verified_capture_without_capturing_again(tmp_path):
    paypal = APIFakePayPal()
    client = make_client(tmp_path, paypal=paypal)
    _, token = issue(client)

    checkout = submit_paypal_api(client, token)
    assert checkout.status_code == 200, checkout.text
    payment_id = checkout.json()["payment_id"]

    paypal.completed = True
    response = client.post(
        "/v1/paypal/webhook",
        headers=_paypal_webhook_headers(),
        json=_completed_capture_event(paypal),
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "received": True,
        "processed": True,
        "duplicate": False,
        "payment_id": payment_id,
        "status": "captured",
    }
    assert paypal.captured == []
    assert len(paypal.webhook_verifications) == 1

    payment = client.store.get_payment_by_order_id(paypal.order_id)
    assert payment.status.value == "captured"
    assert payment.paypal_capture_id == paypal.capture_id


def test_paypal_webhook_duplicate_delivery_is_idempotent(tmp_path):
    paypal = APIFakePayPal()
    client = make_client(tmp_path, paypal=paypal)
    _, token = issue(client)

    checkout = submit_paypal_api(client, token)
    assert checkout.status_code == 200, checkout.text
    paypal.completed = True
    event = _completed_capture_event(paypal)

    first = client.post(
        "/v1/paypal/webhook",
        headers=_paypal_webhook_headers(),
        json=event,
    )
    second = client.post(
        "/v1/paypal/webhook",
        headers=_paypal_webhook_headers(),
        json=event,
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["duplicate"] is False
    assert second.json()["duplicate"] is True
    assert second.json()["status"] == "captured"
    assert paypal.captured == []

    payment = client.store.get_payment_by_order_id(paypal.order_id)
    assert payment.paypal_capture_id == paypal.capture_id

def test_paypal_webhook_concurrent_duplicate_delivery_is_idempotent(
    tmp_path,
):
    paypal = APIFakePayPal()
    client = make_client(tmp_path, paypal=paypal)
    _, token = issue(client)

    checkout = submit_paypal_api(
        client, token, request_id="concurrent-webhook-payment"
    )
    assert checkout.status_code == 200, checkout.text

    paypal.completed = True
    event = _completed_capture_event(
        paypal, event_id="WH-CONCURRENT-DUPLICATE-1"
    )

    def deliver_webhook(_):
        return client.post(
            "/v1/paypal/webhook",
            headers=_paypal_webhook_headers(),
            json=event,
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        responses = list(executor.map(deliver_webhook, range(8)))

    assert all(
        response.status_code == 200 for response in responses
    ), [response.text for response in responses]

    results = [response.json() for response in responses]

    assert sum(r["duplicate"] is False for r in results) == 1
    assert sum(r["duplicate"] is True for r in results) == 7
    assert all(r["status"] == "captured" for r in results)

    payment = client.store.get_payment_by_order_id(paypal.order_id)
    assert payment.status.value == "captured"
    assert payment.paypal_capture_id == paypal.capture_id
    assert paypal.captured == []

def test_paypal_webhook_rejects_mismatched_capture_amount(tmp_path):
    paypal = APIFakePayPal()
    client = make_client(tmp_path, paypal=paypal)
    _, token = issue(client)

    checkout = submit_paypal_api(client, token)
    assert checkout.status_code == 200, checkout.text

    paypal.completed = True
    event = _completed_capture_event(paypal)
    event["resource"]["amount"]["value"] = "19.99"

    response = client.post(
        "/v1/paypal/webhook",
        headers=_paypal_webhook_headers(),
        json=event,
    )

    assert response.status_code == 400, response.text

    payment = client.store.get_payment_by_order_id(paypal.order_id)
    assert payment.status.value == "awaiting_payer"
    assert payment.paypal_capture_id is None
    assert paypal.captured == []

def test_paypal_webhook_rejects_mismatched_capture_currency(tmp_path):
    paypal = APIFakePayPal()
    client = make_client(tmp_path, paypal=paypal)
    _, token = issue(client)

    checkout = submit_paypal_api(client, token)
    assert checkout.status_code == 200, checkout.text

    paypal.completed = True
    event = _completed_capture_event(paypal)
    event["resource"]["amount"]["currency_code"] = "EUR"

    response = client.post(
        "/v1/paypal/webhook",
        headers=_paypal_webhook_headers(),
        json=event,
    )

    assert response.status_code == 400, response.text

    payment = client.store.get_payment_by_order_id(paypal.order_id)
    assert payment.status.value == "awaiting_payer"
    assert payment.paypal_capture_id is None
    assert paypal.captured == []

def test_paypal_webhook_rejects_mismatched_order_id(tmp_path):
    paypal = APIFakePayPal()
    client = make_client(tmp_path, paypal=paypal)
    _, token = issue(client)

    checkout = submit_paypal_api(client, token)
    assert checkout.status_code == 200, checkout.text

    paypal.completed = True
    event = _completed_capture_event(paypal)
    event["resource"]["supplementary_data"]["related_ids"][
        "order_id"
    ] = "ORDER-ATTACKER-999"

    response = client.post(
        "/v1/paypal/webhook",
        headers=_paypal_webhook_headers(),
        json=event,
    )

    assert response.status_code == 404, response.text

    payment = client.store.get_payment_by_order_id(paypal.order_id)
    assert payment.status.value == "awaiting_payer"
    assert payment.paypal_capture_id is None
    assert paypal.captured == []

def test_paypal_webhook_rejects_provider_order_not_completed(tmp_path):
    paypal = APIFakePayPal()
    client = make_client(tmp_path, paypal=paypal)
    _, token = issue(client)

    checkout = submit_paypal_api(client, token)
    assert checkout.status_code == 200, checkout.text

    # Event claims completion, but the provider still reports APPROVED.
    paypal.completed = False
    event = _completed_capture_event(paypal)

    response = client.post(
        "/v1/paypal/webhook",
        headers=_paypal_webhook_headers(),
        json=event,
    )

    assert response.status_code == 400, response.text

    payment = client.store.get_payment_by_order_id(paypal.order_id)
    assert payment.status.value == "awaiting_payer"
    assert payment.paypal_capture_id is None
    assert paypal.captured == []

def test_paypal_webhook_rejects_event_id_reused_for_different_capture(
    tmp_path,
):
    paypal = APIFakePayPal()
    client = make_client(tmp_path, paypal=paypal)
    _, token = issue(client)

    # First legitimate payment and webhook.
    first_checkout = submit_paypal_api(
        client, token, request_id="event-id-first-payment"
    )
    assert first_checkout.status_code == 200, first_checkout.text

    paypal.completed = True
    first_event = _completed_capture_event(
        paypal, event_id="WH-REUSED-EVENT-ID"
    )
    first_response = client.post(
        "/v1/paypal/webhook",
        headers=_paypal_webhook_headers(),
        json=first_event,
    )

    assert first_response.status_code == 200, first_response.text
    assert first_response.json()["duplicate"] is False

    # A different order and capture, but the same webhook event ID.
    paypal.order_id = "ORDER-API-SECOND"
    paypal.capture_id = "CAPTURE-API-SECOND"

    second_checkout = submit_paypal_api(
        client, token, request_id="event-id-second-payment"
    )
    assert second_checkout.status_code == 200, second_checkout.text

    second_payment_id = second_checkout.json()["payment_id"]

    second_event = _completed_capture_event(
        paypal, event_id="WH-REUSED-EVENT-ID"
    )
    second_response = client.post(
        "/v1/paypal/webhook",
        headers=_paypal_webhook_headers(),
        json=second_event,
    )

    assert second_response.status_code == 409, second_response.text

    second_payment = client.store.get_payment_by_order_id(
        paypal.order_id
    )
    assert second_payment.payment_id == second_payment_id
    assert second_payment.status.value == "awaiting_payer"
    assert second_payment.paypal_capture_id is None

    first_payment = client.store.get_payment_by_order_id("ORDER-API-1")
    assert first_payment.status.value == "captured"
    assert first_payment.paypal_capture_id == "CAPTURE-API-1"

    # Webhook reconciliation never initiates a second capture.
    assert paypal.captured == []


def test_paypal_webhook_rejects_capture_owned_by_another_payment(tmp_path):
    paypal = APIFakePayPal()
    client = make_client(tmp_path, paypal=paypal)
    _, token = issue(client)

    first_checkout = submit_paypal_api(client, token, request_id="first-payment")
    assert first_checkout.status_code == 200, first_checkout.text
    first_payment_id = first_checkout.json()["payment_id"]

    # Simulate the first payment having been captured through the browser
    # return path, before any webhook event was recorded for it.
    with client.store._db.transaction() as conn:
        conn.execute(
            "UPDATE payments SET status = ?, paypal_capture_id = ? "
            "WHERE payment_id = ?",
            ("captured", paypal.capture_id, first_payment_id),
        )

    paypal.order_id = "ORDER-API-2"
    second_checkout = submit_paypal_api(
        client, token, request_id="second-payment"
    )
    assert second_checkout.status_code == 200, second_checkout.text
    second_payment_id = second_checkout.json()["payment_id"]

    paypal.completed = True
    response = client.post(
        "/v1/paypal/webhook",
        headers=_paypal_webhook_headers(),
        json=_completed_capture_event(
            paypal, event_id="WH-COLLIDING-CAPTURE-1"
        ),
    )

    assert response.status_code == 409, response.text
    second_payment = client.store.get_payment_by_order_id(paypal.order_id)
    assert second_payment.payment_id == second_payment_id
    assert second_payment.status.value == "awaiting_payer"
    assert second_payment.paypal_capture_id is None
    assert paypal.captured == []


def test_paypal_webhook_rejects_invalid_signature_without_mutation(tmp_path):
    paypal = APIFakePayPal()
    paypal.webhook_signature_valid = False
    client = make_client(tmp_path, paypal=paypal)
    _, token = issue(client)

    checkout = submit_paypal_api(client, token)
    assert checkout.status_code == 200, checkout.text
    paypal.completed = True

    response = client.post(
        "/v1/paypal/webhook",
        headers=_paypal_webhook_headers(),
        json=_completed_capture_event(paypal),
    )

    assert response.status_code == 401, response.text
    payment = client.store.get_payment_by_order_id(paypal.order_id)
    assert payment.status.value == "awaiting_payer"
    assert payment.paypal_capture_id is None
    assert paypal.captured == []


def test_paypal_webhook_acknowledges_verified_unsupported_event(tmp_path):
    paypal = APIFakePayPal()
    client = make_client(tmp_path, paypal=paypal)
    _, token = issue(client)

    checkout = submit_paypal_api(client, token)
    assert checkout.status_code == 200, checkout.text

    response = client.post(
        "/v1/paypal/webhook",
        headers=_paypal_webhook_headers(),
        json={
            "id": "WH-UNSUPPORTED-1",
            "event_type": "CHECKOUT.ORDER.APPROVED",
            "resource": {},
        },
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "received": True,
        "processed": False,
        "duplicate": False,
        "reason": "unsupported_event_type",
    }
    payment = client.store.get_payment_by_order_id(paypal.order_id)
    assert payment.status.value == "awaiting_payer"
    assert paypal.captured == []


def test_corrupted_audit_blocks_paypal_checkout_api(tmp_path):
    paypal = APIFakePayPal()
    client = make_client(
        tmp_path,
        paypal=paypal,
        raise_exceptions=False,
    )
    _, token = issue(client)

    corrupt_latest_audit_hash(client)

    response = submit_paypal_api(
        client,
        token,
        request_id="corrupt-audit-checkout",
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Payment operations are temporarily disabled due to an integrity check failure."
    }
    assert paypal.created == []
    assert paypal.captured == []
    assert client.store.verify_audit().ok is False


def test_corrupted_audit_blocks_paypal_capture_api(tmp_path):
    paypal = APIFakePayPal()
    client = make_client(
        tmp_path,
        paypal=paypal,
        raise_exceptions=False,
    )
    _, token = issue(client)

    checkout = submit_paypal_api(client, token)
    assert checkout.status_code == 200, checkout.text
    assert len(paypal.created) == 1

    corrupt_latest_audit_hash(client)

    response = client.get(
        "/v1/paypal/return",
        params={"token": paypal.order_id},
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Payment operations are temporarily disabled due to an integrity check failure."
    }
    assert paypal.captured == []
    assert client.store.verify_audit().ok is False


def test_paypal_api_rejects_wrong_merchant_without_capture(tmp_path):
    paypal = APIFakePayPal(merchant_id="ATTACKER-MERCHANT")
    client = make_client(
        tmp_path,
        paypal=paypal,
        raise_exceptions=False,
    )
    _, token = issue(client)

    checkout = submit_paypal_api(client, token)
    assert checkout.status_code == 200, checkout.text

    response = client.get(
        "/v1/paypal/return",
        params={"token": paypal.order_id},
    )

    assert response.status_code == 500
    assert paypal.captured == []


def test_paypal_api_cancel_releases_unapproved_checkout(tmp_path):
    paypal = APIFakePayPal()
    paypal.order_status = "VOIDED"
    client = make_client(tmp_path, paypal=paypal)
    _, token = issue(client)

    checkout = submit_paypal_api(client, token)
    assert checkout.status_code == 200, checkout.text

    response = client.get(
        "/v1/paypal/cancel",
        params={"token": paypal.order_id},
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "cancelled"
    assert response.json()["payment_id"] == checkout.json()["payment_id"]
    assert paypal.captured == []


def test_duplicate_paypal_api_cancellation_is_idempotent(tmp_path):
    paypal = APIFakePayPal()
    paypal.order_status = "VOIDED"
    client = make_client(tmp_path, paypal=paypal)
    _, token = issue(client)

    checkout = submit_paypal_api(client, token)
    assert checkout.status_code == 200, checkout.text

    first = client.get(
        "/v1/paypal/cancel",
        params={"token": paypal.order_id},
    )
    second = client.get(
        "/v1/paypal/cancel",
        params={"token": paypal.order_id},
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["status"] == "cancelled"
    assert second.json()["status"] == "cancelled"
    assert paypal.captured == []


def test_paypal_api_does_not_cancel_approved_order(tmp_path):
    paypal = APIFakePayPal()
    paypal.order_status = "APPROVED"
    client = make_client(
        tmp_path,
        paypal=paypal,
        raise_exceptions=False,
    )
    _, token = issue(client)

    checkout = submit_paypal_api(client, token)
    assert checkout.status_code == 200, checkout.text

    response = client.get(
        "/v1/paypal/cancel",
        params={"token": paypal.order_id},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "PayPal order is not in a cancellable state"
    assert paypal.captured == []

def test_paypal_webhook_rejects_malformed_json_without_mutation(tmp_path):
    paypal = APIFakePayPal()
    client = make_client(tmp_path, paypal=paypal)

    response = client.post(
        "/v1/paypal/webhook",
        headers={
            **_paypal_webhook_headers(),
            "content-type": "application/json",
        },
        content=b'{"id":',
    )

    assert response.status_code == 400
    assert paypal.webhook_verifications == []


def test_paypal_webhook_rejects_oversized_body(tmp_path):
    paypal = APIFakePayPal()
    client = make_client(tmp_path, paypal=paypal)

    response = client.post(
        "/v1/paypal/webhook",
        headers={
            **_paypal_webhook_headers(),
            "content-type": "application/json",
        },
        content=b"x" * (256 * 1024 + 1),
    )

    assert response.status_code == 413
    assert paypal.webhook_verifications == []


def test_paypal_webhook_rejects_wrong_content_type(tmp_path):
    paypal = APIFakePayPal()
    client = make_client(tmp_path, paypal=paypal)

    response = client.post(
        "/v1/paypal/webhook",
        headers={
            **_paypal_webhook_headers(),
            "content-type": "text/plain",
        },
        content=b'{"id":"WH-INVALID"}',
    )

    assert response.status_code == 415
    assert paypal.webhook_verifications == []


def test_paypal_webhook_maps_missing_signature_header_to_400(
    tmp_path, monkeypatch
):
    paypal = APIFakePayPal()
    client = make_client(tmp_path, paypal=paypal)

    def reject_missing_header(headers, event, raw_event_body):
        assert not headers.get("PAYPAL-TRANSMISSION-SIG")
        raise ValueError("Missing or invalid PayPal header")

    monkeypatch.setattr(
        paypal, "verify_webhook_signature", reject_missing_header
    )

    headers = _paypal_webhook_headers()
    headers.pop("PAYPAL-TRANSMISSION-SIG")

    response = client.post(
        "/v1/paypal/webhook",
        headers=headers,
        json={"id": "WH-MISSING-HEADER"},
    )

    assert response.status_code == 400


def test_paypal_webhook_maps_verification_outage_to_503(
    tmp_path, monkeypatch
):
    paypal = APIFakePayPal()
    client = make_client(tmp_path, paypal=paypal)

    def verification_unavailable(headers, event, raw_event_body):
        raise RuntimeError("simulated PayPal verification outage")

    monkeypatch.setattr(
        paypal, "verify_webhook_signature", verification_unavailable
    )

    response = client.post(
        "/v1/paypal/webhook",
        headers=_paypal_webhook_headers(),
        json={"id": "WH-VERIFICATION-OUTAGE"},
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "PayPal webhook processing is temporarily unavailable"
    }
    assert "simulated PayPal" not in response.text

def test_agent_cannot_spoof_agent_id_in_payment_request(client):
    _, token = issue(client, agent_id="agent-1")

    response = pay(client, token, agent_id="agent-2")

    # Extra identity fields must never override the signed mandate.
    assert response.status_code in (200, 422)

    if response.status_code == 200:
        assert response.json()["agent_id"] == "agent-1"


def test_agent_cannot_spoof_agent_id_in_payment_request(client):
    _, token = issue(client, agent_id='agent-1')
    response = pay(client, token, agent_id='agent-2')
    assert response.status_code in (200, 422)
    if response.status_code == 200:
        assert response.json()['agent_id'] == 'agent-1'

def test_basic_auth_scheme_is_rejected_for_admin_endpoint(client):
    response = client.get(
        "/v1/audit/verify",
        headers={"Authorization": "Basic YWRtaW46cGFzcw=="},
    )
    assert response.status_code == 401

def test_payment_endpoint_returns_429_after_rate_limit(client):
    responses = [
        client.post("/v1/payments")
        for _ in range(31)
    ]

    assert all(response.status_code != 429 for response in responses[:30])
    assert responses[30].status_code == 429
    assert int(responses[30].headers["Retry-After"]) > 0
    assert responses[30].json() == {
        "detail": "Too many requests. Please try again later."
    }

def test_api_rejects_request_body_over_one_megabyte(client):
 response = client.post(
"/v1/payments",
content=b"x" * (1024 * 1024 + 1),
headers={"Content-Type": "application/json"},
)
 assert response.status_code == 413
 assert response.json() == {"detail": "Request body too large"}

def test_api_rejects_request_body_over_one_megabyte(client):
    response = client.post(
        "/v1/payments",
        content=b"x" * (1024 * 1024 + 1),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json() == {"detail": "Request body too large"}
