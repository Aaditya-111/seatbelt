from seatbelt.service.rate_limit import InMemoryRateLimiter


def test_rate_limiter_enforces_sliding_window_and_recovers():
    now = [100.0]
    limiter = InMemoryRateLimiter(clock=lambda: now[0])

    assert limiter.allow("client-a", limit=2, window_seconds=10) == (True, 0)
    assert limiter.allow("client-a", limit=2, window_seconds=10) == (True, 0)

    allowed, retry_after = limiter.allow(
        "client-a", limit=2, window_seconds=10
    )
    assert allowed is False
    assert retry_after == 10

    now[0] = 110.1
    assert limiter.allow("client-a", limit=2, window_seconds=10) == (True, 0)


def test_rate_limiter_keeps_clients_independent():
    limiter = InMemoryRateLimiter(clock=lambda: 100.0)

    assert limiter.allow("client-a", limit=1, window_seconds=60) == (True, 0)
    assert limiter.allow("client-b", limit=1, window_seconds=60) == (True, 0)


def test_rate_limiter_rejects_invalid_configuration():
    limiter = InMemoryRateLimiter()

    try:
        limiter.allow("client-a", limit=0, window_seconds=60)
    except ValueError:
        pass
    else:
        raise AssertionError("Expected invalid rate-limit configuration to fail")
