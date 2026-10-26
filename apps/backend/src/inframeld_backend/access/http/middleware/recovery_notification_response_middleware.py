from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RecoveryNotificationResponseMiddleware:
    """Prevent recovery callback responses from being cached."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_private_response(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() not in (b"cache-control", b"pragma")
                ]
                headers.extend([(b"cache-control", b"no-store"), (b"pragma", b"no-cache")])
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_private_response)
