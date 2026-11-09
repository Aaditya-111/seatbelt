import pytest
from pydantic import ValidationError

from seatbelt.config import Settings

BASE = dict(
    _env_file=None,
    paypal_client_id="id",
    paypal_client_secret="secret",
    paypal_return_url="https://a.test/ok",
    paypal_cancel_url="https://a.test/no",
    mandate_signing_key="k" * 40,
    admin_api_key="a" * 30,
)


def test_defaults_to_sandbox():
    s = Settings(**BASE)
    assert s.paypal_env == "sandbox"
    assert s.paypal_base_url == "https://api-m.sandbox.paypal.com"


def test_live_is_blocked_without_opt_in():
    with pytest.raises(ValidationError, match="blocked"):
        Settings(**BASE, paypal_env="live")


def test_live_allowed_with_explicit_opt_in():
    s = Settings(
        **BASE,
        paypal_env="live",
        allow_live=True,
        paypal_expected_merchant_id="live-merchant",
        paypal_webhook_id="live-webhook",
    )
    assert s.paypal_base_url == "https://api-m.paypal.com"


def test_live_requires_expected_merchant_id():
    with pytest.raises(ValidationError, match="PAYPAL_EXPECTED_MERCHANT_ID"):
        Settings(
            **BASE,
            paypal_env="live",
            allow_live=True,
            paypal_webhook_id="live-webhook",
        )


def test_live_requires_webhook_id():
    with pytest.raises(ValidationError, match="PAYPAL_WEBHOOK_ID"):
        Settings(
            **BASE,
            paypal_env="live",
            allow_live=True,
            paypal_expected_merchant_id="live-merchant",
        )


def test_live_requires_https_callback_urls():
    with pytest.raises(ValidationError, match="HTTPS"):
        Settings(
            **{**BASE, "paypal_return_url": "http://a.test/ok"},
            paypal_env="live",
            allow_live=True,
            paypal_expected_merchant_id="live-merchant",
            paypal_webhook_id="live-webhook",
        )


def test_missing_credentials_fail_loudly(monkeypatch):
    for k in ("PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None, paypal_return_url="https://a.test", paypal_cancel_url="https://a.test"
        )


def test_secrets_are_not_printed():
    s = Settings(
        **{**BASE, "paypal_client_secret": "S3CR3T-VALUE-xyz", "paypal_client_id": "ID-VALUE-abc"}
    )
    for text in (repr(s), str(s)):
        assert "S3CR3T-VALUE-xyz" not in text
        assert "ID-VALUE-abc" not in text


def test_invalid_url_rejected():
    with pytest.raises(ValidationError):
        Settings(**{**BASE, "paypal_return_url": "not-a-url"})


def test_short_signing_key_rejected():
    with pytest.raises(ValidationError, match="at least 32"):
        Settings(**{**BASE, "mandate_signing_key": "too-short"})



def test_store_and_policy_defaults():
    s = Settings(**BASE)
    assert s.database_path == "seatbelt.db"
    assert str(s.policy_budget_alert_ratio) == "0.8"


@pytest.mark.parametrize("bad", ["0", "1.5", "-1"])
def test_policy_budget_alert_ratio_bounds(bad):
    with pytest.raises(ValidationError):
        Settings(**{**BASE, "policy_budget_alert_ratio": bad})


def test_short_admin_key_rejected():
    with pytest.raises(ValidationError, match="at least 24"):
        Settings(**{**BASE, "admin_api_key": "short"})


def test_admin_key_must_differ_from_signing_key():
    with pytest.raises(ValidationError, match="different"):
        Settings(**{**BASE, "admin_api_key": "k" * 40})


def test_server_defaults_are_local_only():
    s = Settings(**BASE)
    assert (s.server_host, s.server_port) == ("127.0.0.1", 8000)


@pytest.mark.parametrize("bad", ["0", "70000"])
def test_server_port_bounds(bad):
    with pytest.raises(ValidationError):
        Settings(**{**BASE, "server_port": bad})

@pytest.mark.parametrize("field", ["paypal_client_id", "paypal_client_secret"])
@pytest.mark.parametrize("bad", ["", "   ", " value", "value "])
def test_paypal_credentials_reject_blank_or_padded_values(field, bad):
    with pytest.raises(ValidationError):
        Settings(**{**BASE, field: bad})


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("mandate_signing_key", " " * 40),
        ("mandate_signing_key", " " + "k" * 39),
        ("mandate_signing_key", "k" * 39 + " "),
        ("admin_api_key", " " * 30),
        ("admin_api_key", " " + "a" * 29),
        ("admin_api_key", "a" * 29 + " "),
    ],
)
def test_security_keys_reject_blank_or_padded_values(field, bad):
    with pytest.raises(ValidationError):
        Settings(**{**BASE, field: bad})
