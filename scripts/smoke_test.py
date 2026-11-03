"""End-to-end sandbox check using the real client.

Usage: python scripts/smoke_test.py [--amount 10.00] [--currency USD]
"""

from __future__ import annotations

import argparse
import sys
import uuid

from seatbelt.config import get_settings
from seatbelt.errors import PayPalError
from seatbelt.logging_setup import configure_logging
from seatbelt.paypal import Money, PayPalClient


def main() -> int:
    parser = argparse.ArgumentParser(description="PayPal sandbox smoke test")
    parser.add_argument("--amount", default="10.00")
    parser.add_argument("--currency", default="USD")
    args = parser.parse_args()

    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)

    try:
        with PayPalClient(settings) as paypal:
            order = paypal.create_order(
                Money(amount=args.amount, currency=args.currency),
                description="Seatbelt smoke test",
                reference_id=f"smoke-{uuid.uuid4().hex[:8]}",
            )
            print(f"Created order {order.id} ({order.status})")
            print(f"\nApprove it as your SANDBOX PERSONAL buyer:\n  {order.approve_url}\n")
            input("Press Enter AFTER you land on the return page... ")

            current = paypal.get_order(order.id)
            print(f"PayPal reports order status: {current.status}")
            if current.status != "APPROVED":
                print("Order is not approved yet; finish the approval and run again.")
                return 1

            result = paypal.capture_order(order.id)
            print(f"Captured {result.amount} {result.currency}, capture id {result.capture_id}")
            return 0
    except PayPalError as exc:
        print(
            f"PayPal error: {exc} (status={exc.status_code}, debug_id={exc.debug_id}, "
            f"issues={exc.issues})"
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())