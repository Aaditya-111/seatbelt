import asyncio

from seatbelt.service.request_limits import RequestBodyLimitMiddleware


def run_middleware(app, messages, *, path="/test", limit=1024):
    sent = []
    message_iter = iter(messages)

    async def receive():
        return next(message_iter)

    async def send(message):
        sent.append(message)

    async def run():
        middleware = RequestBodyLimitMiddleware(
            app,
            max_body_bytes=limit,
            paypal_webhook_max_body_bytes=256,
        )
        await middleware(
            {"type": "http", "method": "POST", "path": path},
            receive,
            send,
        )

    asyncio.run(run())
    return sent


def test_request_body_limit_rejects_oversized_chunked_body():
    app_called = False

    async def app(scope, receive, send):
        nonlocal app_called
        app_called = True

    sent = run_middleware(
        app,
        [
            {"type": "http.request", "body": b"a" * 700, "more_body": True},
            {"type": "http.request", "body": b"b" * 325, "more_body": False},
        ],
    )

    assert app_called is False
    assert sent[0]["status"] == 413
    assert sent[1]["body"] == b'{"detail":"Request body too large"}'


def test_paypal_webhook_uses_smaller_body_limit():
    app_called = False

    async def app(scope, receive, send):
        nonlocal app_called
        app_called = True

    sent = run_middleware(
        app,
        [
            {"type": "http.request", "body": b"a" * 200, "more_body": True},
            {"type": "http.request", "body": b"b" * 57, "more_body": False},
        ],
        path="/v1/paypal/webhook",
        limit=1024,
    )

    assert app_called is False
    assert sent[0]["status"] == 413


def test_request_body_limit_replays_valid_body():
    received = []

    async def app(scope, receive, send):
        message = await receive()
        received.append(message["body"])
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [],
        })
        await send({
            "type": "http.response.body",
            "body": b"ok",
        })

    sent = run_middleware(
        app,
        [
            {
                "type": "http.request",
                "body": b'{"amount":"5.00"}',
                "more_body": False,
            }
        ],
    )

    assert received == [b'{"amount":"5.00"}']
    assert sent[0]["status"] == 200


def test_request_body_limit_rejects_invalid_configuration():
    async def app(scope, receive, send):
        pass

    try:
        RequestBodyLimitMiddleware(app, max_body_bytes=0)
    except ValueError:
        pass
    else:
        raise AssertionError("Expected invalid body limit to fail")
