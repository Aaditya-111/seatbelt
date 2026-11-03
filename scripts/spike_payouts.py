"""THROWAWAY SPIKE: can this sandbox send a server-side payout (no browser approval)?

Sends one small payout from your sandbox business account to a sandbox email, then reports
what happened in plain language. Delete this file once the real executor exists.

Usage:
  python scripts/spike_payouts.py --receiver <sandbox personal account email>
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid
from collections.abc import Callable
from typing import Any

import httpx

from seatbelt.config import Settings, get_settings

_DONE = {"SUCCESS", "DENIED", "CANCELED", "FAILED"}


def get_token(http: httpx.Client, settings: Settings) -> str:
    resp = http.post(
        "/v1/oauth2/token",
        auth=(
            settings.paypal_client_id.get_secret_value(),
            settings.paypal_client_secret.get_secret_value(),
        ),
        data={"grant_type": "client_credentials"},
    )
    if resp.status_code != 200:
        raise SystemExit(f"Could not get a token (HTTP {resp.status_code}): check your credentials.")
    return resp.json()["access_token"]


def send_payout(
    http: httpx.Client, token: str, *, receiver: str, amount: str, currency: str
) -> httpx.Response:
    batch_id = f"spike-{uuid.uuid4().hex[:16]}"
    body = {
        "sender_batch_header": {
            "sender_batch_id": batch_id,
            "email_subject": "Seatbelt spike payout",
            "recipient_type": "EMAIL",
        },
        "items": [
            {
                "recipient_type": "EMAIL",
                "receiver": receiver,
                "amount": {"value": amount, "currency": currency},
                "note": "Seatbelt sandbox spike",
                "sender_item_id": f"{batch_id}-1",
            }
        ],
    }
    return http.post(
        "/v1/payments/payouts",
        headers={"Authorization": f"Bearer {token}", "PayPal-Request-Id": batch_id},
        json=body,
    )


def get_batch(http: httpx.Client, token: str, batch_id: str) -> dict[str, Any]:
    resp = http.get(
        f"/v1/payments/payouts/{batch_id}", headers={"Authorization": f"Bearer {token}"}
    )
    return resp.json() if resp.content else {}


def explain_failure(resp: httpx.Response) -> str:
    try:
        body = resp.json()
    except ValueError:
        body = {}
    name = body.get("name", "")
    issues = [d.get("issue", "") for d in body.get("details", []) if isinstance(d, dict)]
    summary = f"HTTP {resp.status_code} {name} {issues} {body.get('message', '')}".strip()
    if resp.status_code == 401:
        return f"{summary}\n-> Credentials rejected. Check .env and that you copied SANDBOX keys."
    if resp.status_code == 403 or name in ("NOT_AUTHORIZED", "AUTHORIZATION_ERROR"):
        return (
            f"{summary}\n-> Payouts is probably not enabled for this app. In "
            "developer.paypal.com > Apps & Credentials (Sandbox) > your app, look for a "
            "Features section, tick Payouts, save, then run this again."
        )
    if any("INSUFFICIENT" in i for i in issues) or name == "INSUFFICIENT_FUNDS":
        return f"{summary}\n-> The sandbox business account has too little balance."
    return f"{summary}\n-> Unexpected. Copy this whole message back to me."


def run(
    http: httpx.Client,
    settings: Settings,
    *,
    receiver: str,
    amount: str,
    currency: str,
    sleep: Callable[[float], None] = time.sleep,
    polls: int = 6,
) -> int:
    token = get_token(http, settings)
    resp = send_payout(http, token, receiver=receiver, amount=amount, currency=currency)
    if resp.status_code not in (200, 201):
        print("RESULT: the payout request was REFUSED")
        print(explain_failure(resp))
        return 1

    batch_id = resp.json()["batch_header"]["payout_batch_id"]
    print(f"Payout accepted. batch id: {batch_id}")

    status, items = "PENDING", []
    for _ in range(polls):
        batch = get_batch(http, token, batch_id)
        status = batch.get("batch_header", {}).get("batch_status", "UNKNOWN")
        items = batch.get("items", [])
        print(f"  batch status: {status}")
        if status in _DONE:
            break
        sleep(2)

    for item in items:
        errors = item.get("errors")
        print(
            f"  item {item.get('payout_item_id')}: {item.get('transaction_status')}"
            + (f"  errors: {errors}" if errors else "")
        )

    if status == "SUCCESS":
        print("RESULT: PAYOUTS WORK in your sandbox. We can build the real executor on this.")
        return 0
    print(f"RESULT: the payout was accepted but ended as {status}. Send me the lines above.")
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Payout capability spike (sandbox only)")
    parser.add_argument("--receiver", required=True, help="a SANDBOX account email")
    parser.add_argument("--amount", default="1.00")
    parser.add_argument("--currency", default="USD")
    args = parser.parse_args(argv)

    settings = get_settings()
    if settings.paypal_env != "sandbox":
        raise SystemExit("Refusing to run: PAYPAL_ENV must be sandbox for this spike.")
    with httpx.Client(base_url=settings.paypal_base_url, timeout=30) as http:
        return run(
            http, settings, receiver=args.receiver, amount=args.amount, currency=args.currency
        )


if __name__ == "__main__":
    sys.exit(main())