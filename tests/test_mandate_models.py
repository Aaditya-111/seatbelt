from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from seatbelt.mandate import Mandate

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)


def make(**overrides):
    base = dict(
        agent_id="agent-1",
        currency="USD",
        per_payment_limit="100",
        total_limit="500",
        approval_threshold="50",
        allowed_payees=["Shop-A", "shop-b"],
        issued_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )
    base.update(overrides)
    return Mandate(**base)


def test_valid_mandate_normalises_payees():
    m = make(allowed_payees=["Shop-B", " shop-a ", "SHOP-A"])
    assert m.allowed_payees == ("shop-a", "shop-b")


@pytest.mark.parametrize("bad", ["*", "shop-*", ""])
def test_wildcards_and_blanks_rejected(bad):
    with pytest.raises(ValidationError):
        make(allowed_payees=[bad])


def test_payee_list_cannot_be_empty():
    with pytest.raises(ValidationError):
        make(allowed_payees=[])


def test_payees_must_be_a_list_not_a_string():
    with pytest.raises(ValidationError):
        make(allowed_payees="shop-a")


def test_floats_rejected():
    with pytest.raises(ValidationError):
        make(per_payment_limit=99.9)


def test_per_payment_limit_cannot_exceed_total():
    with pytest.raises(ValidationError, match="per_payment_limit"):
        make(per_payment_limit="600", total_limit="500")


def test_threshold_cannot_exceed_per_payment_limit():
    with pytest.raises(ValidationError, match="approval_threshold"):
        make(approval_threshold="150")


def test_zero_threshold_means_always_ask_and_is_allowed():
    assert make(approval_threshold="0").approval_threshold == 0


def test_expiry_must_follow_issue_time():
    with pytest.raises(ValidationError, match="expires_at"):
        make(expires_at=NOW)


def test_naive_datetimes_rejected():
    with pytest.raises(ValidationError, match="timezone-aware"):
        make(issued_at=datetime(2026, 10, 10, 12, 0))


def test_unknown_fields_rejected():
    with pytest.raises(ValidationError):
        make(sneaky_extra="x")


def test_mandate_is_immutable():
    m = make()
    with pytest.raises(ValidationError):
        m.total_limit = 999999