"""Start the Seatbelt guard server.

NOTE: until the PayPal executor is added (next step), payments are SIMULATED: the guard makes
every decision for real, but no money moves and PayPal is never called.

Usage: python scripts/run_server.py
Then open http://127.0.0.1:8000/docs
"""

from __future__ import annotations

from datetime import timedelta

import uvicorn

from seatbelt.config import get_settings
from seatbelt.logging_setup import configure_logging
from seatbelt.policy import PolicyConfig
from seatbelt.service import FakeExecutor, GuardService, create_app
from seatbelt.store import Database, GuardStore


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)

    db = Database(settings.database_path)
    db.initialize()
    store = GuardStore(
        db,
        settings.mandate_signing_key,
        policy_config=PolicyConfig(budget_alert_ratio=settings.policy_budget_alert_ratio),
    )
    service = GuardService(
        store,
        FakeExecutor(),
        settings.mandate_signing_key,
        max_mandate_ttl=timedelta(hours=settings.mandate_max_ttl_hours),
    )
    app = create_app(service, settings.admin_api_key)

    print("=" * 64)
    print(" Seatbelt guard  |  SIMULATED payments (no PayPal calls yet)")
    print(f" API docs:  http://{settings.server_host}:{settings.server_port}/docs")
    print("=" * 64)
    uvicorn.run(
        app,
        host=settings.server_host,
        port=settings.server_port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()