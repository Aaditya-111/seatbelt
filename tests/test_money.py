from decimal import Decimal

import pytest
from pydantic import ValidationError

from seatbelt.paypal.models import Money


def test_formats_two_decimals():
    assert Money(amount="10", currency="USD").to_paypal_value() == "10.00"
    assert Money(amount=Decimal("10.005"), currency="USD").to_paypal_value() == "10.01"


def test_zero_decimal_currency():
    assert Money(amount="1500", currency="JPY").to_paypal_value() == "1500"


def test_rejects_floats():
    with pytest.raises(ValidationError):
        Money(amount=10.1, currency="USD")


@pytest.mark.parametrize("bad", ["0", "-5"])
def test_rejects_non_positive(bad):
    with pytest.raises(ValidationError):
        Money(amount=bad, currency="USD")


@pytest.mark.parametrize("bad", ["usd", "US", "USDD", "12A"])
def test_rejects_bad_currency(bad):
    with pytest.raises(ValidationError):
        Money(amount="1", currency=bad)


def test_amount_that_rounds_to_zero_rejected_at_format_time():
    with pytest.raises(ValueError):
        Money(amount="0.001", currency="USD").to_paypal_value()