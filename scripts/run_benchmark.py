"""Run Seatbelt-Bench: hostile scenarios against an unprotected agent and against Seatbelt.

  python scripts/run_benchmark.py
  python scripts/run_benchmark.py --out docs/BENCHMARK.md --json docs/benchmark_results.json

Exit code is 1 if any attack moves unauthorised money through Seatbelt, or any legitimate-use
check fails, so this can gate a release or CI job.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

from seatbelt.bench import render_markdown, run_all, summarise


def _jsonable(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"not serialisable: {type(value)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Seatbelt benchmark")
    parser.add_argument("--out", help="write the Markdown report to this path")
    parser.add_argument("--json", dest="json_path", help="write machine-readable results here")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        attacks, benign = run_all(Path(tmp))

    report = render_markdown(attacks, benign)
    print(report)
    summary = summarise(attacks, benign)

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(report, encoding="utf-8")
        print(f"[wrote {args.out}]")
    if args.json_path:
        Path(args.json_path).parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "summary": summary,
            "attacks": [
                {
                    "id": a.attack.id,
                    "name": a.attack.name,
                    "category": a.attack.category,
                    "unprotected": {"lost": a.unprotected.lost, "moved": a.unprotected.moved},
                    "seatbelt": {
                        "lost": a.guarded.lost,
                        "moved": a.guarded.moved,
                        "outcomes": a.guarded.outcomes,
                    },
                }
                for a in attacks
            ],
            "legitimate_use": [
                {"check": b.name, "passed": b.passed, "detail": b.detail} for b in benign
            ],
        }
        Path(args.json_path).write_text(
            json.dumps(payload, indent=2, default=_jsonable), encoding="utf-8"
        )
        print(f"[wrote {args.json_path}]")

    failed = summary["seatbelt_attacks_succeeded"] or (
        summary["benign_passed"] != summary["benign_checks"]
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())