from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from seatbelt.service import ExecutionResult, FakeExecutor, GuardService, create_app
from seatbelt.store import Database, GuardStore

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


def make_client(tmp_path, executor=None, raise_exceptions=True):
    db = Database(tmp_path / "api.db")
    db.initialize()
    clock = Clock()
    service = GuardService(
        GuardStore(db, SIGNING_KEY),
        executor or FakeExecutor(),
        SIGNING_KEY,
        max_mandate_ttl=timedelta(hours=24),
        clock=clock,
    )
    app = create_app(service, SecretStr(ADMIN_KEY))
    client = TestClient(app, raise_server_exceptions=raise_exceptions)
    client.clock = clock
    client.executor = service._executor
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