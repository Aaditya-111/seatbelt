import pytest

from seatbelt.config import Settings


@pytest.fixture(autouse=True)
def _isolate_environment(monkeypatch):
    """Tests must not depend on whatever settings happen to be in the developer's shell."""
    for field in Settings.model_fields:
        monkeypatch.delenv(field.upper(), raising=False)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        paypal_client_id="test-id",
        paypal_client_secret="test-secret",
        paypal_return_url="https://app.test/success",
        paypal_cancel_url="https://app.test/cancel",
        paypal_max_retries=2,
        mandate_signing_key="k" * 40,
        admin_api_key="a" * 30,
    )