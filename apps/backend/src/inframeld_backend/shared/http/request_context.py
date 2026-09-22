"""Attach request-scoped correlation data to HTTP requests.

This middleware creates a request identifier for each HTTP request and makes it
available in two places:

* ``request.state.request_id`` for FastAPI route handlers.
* Structlog's context-local values for log messages emitted during the request.

It also records the response status and duration, adds the request identifier to
the response headers, and clears the context when the request finishes so that
values cannot leak into another request handled by the same process.
"""

from time import perf_counter
from uuid import uuid4

import structlog
from starlette.routing import Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from structlog.contextvars import bind_contextvars, clear_contextvars

from inframeld_backend.shared.infrastructure.error_reporting import report_unexpected_error
from inframeld_backend.shared.infrastructure.timing import elapsed_milliseconds

logger = structlog.get_logger(__name__)


class RequestContextMiddleware:
    """Add request identity and lifecycle logging to an ASGI application.

    The middleware is deliberately implemented at the ASGI level so it can
    wrap the whole application and observe the response before it is sent to
    the client. Non-HTTP scopes, such as WebSocket or lifespan events, pass
    through unchanged.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Initialize the middleware around the application being wrapped."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Process one ASGI scope and add context when it represents HTTP."""
        if scope["type"] != "http":
            # The application may also receive WebSocket and lifespan scopes.
            # They do not represent an HTTP request, so they need no request
            # ID or HTTP response logging from this middleware.
            await self.app(scope, receive, send)
            return

        # Generate the identifier inside the application. We do not trust an
        # arbitrary incoming header to define the identity of our request.
        request_id = str(uuid4())
        started_at = perf_counter()
        status_code: int | None = None

        # ``scope["state"]`` is exposed by Starlette as ``request.state``.
        # This gives route handlers access to the same ID that appears in logs.
        scope.setdefault("state", {})["request_id"] = request_id

        # Context variables are local to the current async execution context.
        # Clear first so a reused worker cannot carry values from an earlier
        # request, then bind values that should appear in every log entry.
        clear_contextvars()
        bind_contextvars(
            request_id=request_id,
            http_method=scope.get("method"),
        )

        async def send_with_context(message: Message) -> None:
            """Capture response status and add the request ID to its headers."""
            nonlocal status_code

            if message["type"] == "http.response.start":
                # The response-start message contains the status and headers.
                # Add our correlation header before forwarding that message.
                status_code = int(message["status"])

                headers = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() != b"x-request-id"
                ]

                headers.append((b"x-request-id", request_id.encode("ascii")))

                message = {
                    **message,
                    "headers": headers,
                }

            await send(message)

        try:
            await self.app(scope, receive, send_with_context)
        except Exception as error:
            # The request boundary owns the primary unexpected-error
            # diagnostic. Marking the exact exception prevents an outer
            # handler or server logger from reporting it again.
            report_unexpected_error(
                error,
                event="request_failed",
                duration_ms=elapsed_milliseconds(started_at),
                status_code=status_code,
            )
            raise
        else:
            # Routing has finished, so a matched route is now available in
            # the scope. Its pattern is safe to log; the requested path is not.
            route = scope.get("route")
            context: dict[str, object] = {
                "status_code": status_code,
                "duration_ms": elapsed_milliseconds(started_at),
            }

            if isinstance(route, Route):
                context["http_route"] = route.path_format

            logger.info("request_completed", **context)
        finally:
            # Never allow request data to escape into a later request context.
            clear_contextvars()
