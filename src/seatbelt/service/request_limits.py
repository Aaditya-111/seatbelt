from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestBodyLimitMiddleware:
    """Reject oversized HTTP request bodies before application parsing."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        max_body_bytes: int,
        paypal_webhook_max_body_bytes: int = 256 * 1024,
    ) -> None:
        if max_body_bytes < 1 or paypal_webhook_max_body_bytes < 1:
            raise ValueError("Request body limits must be positive")

        self.app = app
        self.max_body_bytes = max_body_bytes
        self.paypal_webhook_max_body_bytes = paypal_webhook_max_body_bytes

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        body_limit = (
            self.paypal_webhook_max_body_bytes
            if scope.get("path") == "/v1/paypal/webhook"
            else self.max_body_bytes
        )

        body = bytearray()

        while True:
            message = await receive()

            if message["type"] == "http.disconnect":
                return

            if message["type"] != "http.request":
                continue

            chunk = message.get("body", b"")

            if len(body) + len(chunk) > body_limit:
                response_body = b'{"detail":"Request body too large"}'
                await send({
                    "type": "http.response.start",
                    "status": 413,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (
                            b"content-length",
                            str(len(response_body)).encode("ascii"),
                        ),
                    ],
                })
                await send({
                    "type": "http.response.body",
                    "body": response_body,
                })
                return

            body.extend(chunk)

            if not message.get("more_body", False):
                break

        buffered_body = bytes(body)
        delivered = False

        async def replay_receive() -> Message:
            nonlocal delivered

            if not delivered:
                delivered = True
                return {
                    "type": "http.request",
                    "body": buffered_body,
                    "more_body": False,
                }

            return {"type": "http.disconnect"}

        await self.app(scope, replay_receive, send)
