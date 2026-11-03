"""Watch the policy engine decide on a series of payments. No network or credentials needed.

Usage: python scripts/try_policy.py
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from seatbelt.mandate import Mandate
from seatbelt.paypal.models import Money
from seatbelt.policy import PaymentRequest, RiskSignal, Severity, evaluate


def main() -> None:
    now = datetime.now(timezone.utc)
    mandate = Mandate(
        agent_id="shopper-1",
        currency="USD",
        per_payment_limit="100",
        total_limit="300",
        approval_threshold="40",
        allowed_payees=["shop-a", "shop-b"],
        issued_at=now,
        expires_at=now + timedelta(hours=1),
    )

    hijack = RiskSignal(
        code="injection",
        severity=Severity.HIGH,
        message="Product page contained instructions aimed at the AI agent.",
    )
    scenarios = [
        ("Small purchase from an approved shop", "shop-a", "25.00", ()),
        ("Larger purchase (above the 'ask me' amount)", "shop-b", "75.00", ()),
        ("Over the per-payment limit", "shop-a", "250.00", ()),
        ("Unknown payee", "totally-legit-store", "10.00", ()),
        ("Looks fine, but a page tried to hijack the agent", "shop-a", "10.00", (hijack,)),
    ]

    committed = Decimal("0")
    for i, (title, payee, amount, signals) in enumerate(scenarios, 1):
        request = PaymentRequest(
            request_id=f"demo-{i}",
            agent_id="shopper-1",
            payee=payee,
            money=Money(amount=amount, currency="USD"),
            risk_signals=signals,
        )
        decision = evaluate(mandate, request, committed=committed)
        print(f"\n{i}. {title}\n{decision.explain()}")


if __name__ == "__main__":
    main()