"""Production application composition root."""

from __future__ import annotations

from datetime import timedelta

from fastapi import FastAPI

from seatbelt.config import Settings, get_settings
from seatbelt.paypal.client import PayPalClient
from seatbelt.service.api import create_app
from seatbelt.service.core import GuardService
from seatbelt.store.db import Database
from seatbelt.store.guard import GuardStore


class DisabledExecutor:
    """Fail closed when a non-PayPal payment executor is not configured."""

    def execute(self, payment):
        raise RuntimeError(
            "No production payment executor is configured. "
            "Use the PayPal checkout flow for real payments."
        )


def build_app(settings: Settings | None = None) -> FastAPI:
    """Build the production FastAPI application."""

    config = settings or get_settings()

    database = Database(config.database_path)
    database.initialize()

    store = GuardStore(
        database,
        config.mandate_signing_key,
        audit_checkpoint_path=config.audit_checkpoint_path,
    )
    service = GuardService(
        store,
        DisabledExecutor(),
        config.mandate_signing_key,
        max_mandate_ttl=timedelta(
            hours=config.mandate_max_ttl_hours
        ),
        paypal_client=PayPalClient(config),
        paypal_expected_merchant_id=config.paypal_expected_merchant_id,
    )

    return create_app(
        service,
        config.admin_api_key,
    )
