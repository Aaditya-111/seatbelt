import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

import pytest

from seatbelt.errors import (
    MalformedMandateError,
    MandateError,
    MandateExpiredError,
    MandateNotYetValidError,
    MandateSignatureError,
)
from seatbelt.mandate import decode_mandate, issue_mandate

KEY = "k" * 40
OTHER_KEY = "z" * 40
NOW = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
MAX_TTL = timedelta(hours=24)


def issue(**overrides):
    args = dict(
        key=KEY,
        agent_id="agent-1",
        currency="USD",
        per_payment_limit="100",
        total_limit="500",
        approval_threshold="50",
        allowed_payees=["shop-a"],
        ttl=timedelta(hours=1),
        max_ttl=MAX_TTL,
        now=NOW,
    )
    args.update(overrides)
    return issue_mandate(**args)


def b64d(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def b64e(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def test_round_trip_preserves_every_field():
    mandate, token = issue()
    assert decode_mandate(token, KEY, now=NOW + timedelta(minutes=5)) == mandate


def test_tampering_with_limits_is_detected():
    _, token = issue()
    payload_b64, sig_b64 = token.split(".")
    data = json.loads(b64d(payload_b64))
    data["per_payment_limit"] = "100000"
    data["total_limit"] = "100000"
    forged = b64e(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()) + "." + sig_b64
    with pytest.raises(MandateSignatureError):
        decode_mandate(forged, KEY, now=NOW)


def test_swapping_in_another_mandates_signature_is_detected():
    _, token_a = issue(agent_id="agent-a")
    _, token_b = issue(agent_id="agent-b")
    forged = token_a.split(".")[0] + "." + token_b.split(".")[1]
    with pytest.raises(MandateSignatureError):
        decode_mandate(forged, KEY, now=NOW)


def test_wrong_key_is_rejected():
    _, token = issue()
    with pytest.raises(MandateSignatureError):
        decode_mandate(token, OTHER_KEY, now=NOW)


def test_expired_mandate_is_rejected_at_the_boundary():
    _, token = issue(ttl=timedelta(hours=1))
    decode_mandate(token, KEY, now=NOW + timedelta(minutes=59, seconds=59))
    with pytest.raises(MandateExpiredError):
        decode_mandate(token, KEY, now=NOW + timedelta(hours=1))


def test_not_yet_valid_mandate_is_rejected_but_small_clock_skew_is_tolerated():
    _, token = issue()
    decode_mandate(token, KEY, now=NOW - timedelta(seconds=10))
    with pytest.raises(MandateNotYetValidError):
        decode_mandate(token, KEY, now=NOW - timedelta(minutes=5))


@pytest.mark.parametrize("bad", ["", "abc", "a.b.c", ".", "a.", ".b", "!!!.???"])
def test_malformed_tokens_are_rejected(bad):
    with pytest.raises(MalformedMandateError):
        decode_mandate(bad, KEY, now=NOW)


def test_validly_signed_but_garbage_payload_is_rejected():
    payload = b'{"not": "a mandate"}'
    sig = hmac.new(KEY.encode(), payload, hashlib.sha256).digest()
    with pytest.raises(MalformedMandateError):
        decode_mandate(f"{b64e(payload)}.{b64e(sig)}", KEY, now=NOW)


def test_ttl_longer_than_maximum_is_refused():
    with pytest.raises(MandateError, match="exceeds"):
        issue(ttl=timedelta(hours=25))


@pytest.mark.parametrize("ttl", [timedelta(0), timedelta(seconds=-5)])
def test_non_positive_ttl_is_refused(ttl):
    with pytest.raises(MandateError):
        issue(ttl=ttl)


def test_short_signing_key_is_refused():
    with pytest.raises(MandateError, match="at least"):
        issue(key="short")


def test_invalid_limits_surface_as_mandate_error():
    with pytest.raises(MandateError):
        issue(per_payment_limit="900", total_limit="500")


def test_token_contains_no_secret_material():
    _, token = issue()
    assert KEY not in token
    assert KEY not in b64d(token.split(".")[0]).decode()