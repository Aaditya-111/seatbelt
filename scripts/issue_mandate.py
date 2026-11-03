"""Issue a signed mandate and verify it, to see how mandates behave.

Usage (one line):
  python scripts/issue_mandate.py --agent shopper-1 --per-payment 100 --total 300 --threshold 40 --payee shop-a --payee shop-b
"""

from __future__ import annotations

import argparse
import sys
from datetime import timedelta

from seatbelt.config import get_settings
from seatbelt.errors import MandateError
from seatbelt.mandate import decode_mandate, issue_mandate


def main() -> int:
    p = argparse.ArgumentParser(description="Issue a signed spending mandate")
    p.add_argument("--agent", required=True)
    p.add_argument("--currency", default="USD")
    p.add_argument("--per-payment", required=True)
    p.add_argument("--total", required=True)
    p.add_argument("--threshold", required=True, help="payments above this need human approval")
    p.add_argument("--payee", action="append", required=True, help="repeat for several payees")
    p.add_argument("--ttl-minutes", type=int, default=60)
    args = p.parse_args()

    settings = get_settings()
    try:
        mandate, token = issue_mandate(
            key=settings.mandate_signing_key,
            agent_id=args.agent,
            currency=args.currency,
            per_payment_limit=args.per_payment,
            total_limit=args.total,
            approval_threshold=args.threshold,
            allowed_payees=args.payee,
            ttl=timedelta(minutes=args.ttl_minutes),
            max_ttl=timedelta(hours=settings.mandate_max_ttl_hours),
        )
        verified = decode_mandate(token, settings.mandate_signing_key)
    except MandateError as exc:
        print(f"Could not issue mandate: {exc}")
        return 1

    print(verified.model_dump_json(indent=2))
    print(f"\nToken (give this to the agent):\n{token}")
    return 0


if __name__ == "__main__":
    sys.exit(main())