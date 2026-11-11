import json
from typing import override

from fastapi.routing import APIRoute
from starlette.requests import Request
from starlette.types import Message, Receive, Scope, Send

from inframeld_backend.shared.http.builders.problem_response import build_problem_response
from inframeld_backend.shared.http.definitions.problem_catalogue import INVALID_INPUT_PROBLEM
from inframeld_backend.shared.http.mappers.problem_mapper import for_http_status


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject duplicate JSON fields so the submitted request has one unambiguous meaning."""
    values: dict[str, object] = {}
    for key, value in pairs:
        if key in values:
            raise ValueError("Duplicate JSON field.")
        values[key] = value
    return values


def _reject_constant(_value: str) -> object:
    """Reject non-finite JSON constants before mapping the submitted request."""
    raise ValueError("Invalid JSON constant.")


class ApplicationAccountRoute(APIRoute):
    """Keep exact account operations unambiguous and responses private."""

    @override
    async def handle(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def private_response(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() != b"cache-control"
                ]
                message = {**message, "headers": headers + [(b"cache-control", b"no-store")]}
            await send(message)

        request = Request(scope, receive)
        if scope["method"] == "GET":
            allowed: set[str] = (
                {"name"}
                if self.path.endswith("/resolve")
                else {"limit", "cursor"}
                if self.path.endswith("/keys")
                else set()
            )
            invalid = any(
                key not in allowed or len(request.query_params.getlist(key)) != 1
                for key in request.query_params
            )
            limit = request.query_params.get("limit")
            if limit is not None and (
                not limit.isascii()
                or not limit.isdecimal()
                or len(limit) > 3
                or (len(limit) > 1 and limit.startswith("0"))
            ):
                invalid = True
            if not invalid:
                async for chunk in request.stream():
                    if chunk:
                        invalid = True
                        break
            if invalid:
                await build_problem_response(request, INVALID_INPUT_PROBLEM)(
                    scope, receive, private_response
                )
                return
            await super().handle(scope, receive, private_response)
            return
        if scope["method"] == "DELETE":
            invalid = any(
                key != "expectedAccessRevision" or len(request.query_params.getlist(key)) != 1
                for key in request.query_params
            )
            revision = request.query_params.get("expectedAccessRevision")
            if revision is not None and (
                not revision.isascii()
                or not revision.isdecimal()
                or len(revision) > 16
                or (len(revision) > 1 and revision.startswith("0"))
            ):
                invalid = True
            if not invalid:
                async for chunk in request.stream():
                    if chunk:
                        invalid = True
                        break
            if invalid:
                await build_problem_response(request, INVALID_INPUT_PROBLEM)(
                    scope, receive, private_response
                )
                return
            await super().handle(scope, receive, private_response)
            return
        if scope["method"] != "POST":
            await super().handle(scope, receive, private_response)
            return
        if request.query_params:
            await build_problem_response(request, INVALID_INPUT_PROBLEM)(
                scope, receive, private_response
            )
            return
        if (
            request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            != "application/json"
        ):
            await build_problem_response(request, for_http_status(415))(
                scope, receive, private_response
            )
            return
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > 32768:
                await build_problem_response(request, for_http_status(413))(
                    scope, receive, private_response
                )
                return
            body.extend(chunk)
        try:
            value: object = json.loads(
                body.decode("utf-8"),
                object_pairs_hook=_unique_object,
                parse_constant=_reject_constant,
            )
            if not isinstance(value, dict):
                raise ValueError("Expected a JSON object.")
        except (ValueError, RecursionError):
            await build_problem_response(request, INVALID_INPUT_PROBLEM)(
                scope, receive, private_response
            )
            return
        delivered = False

        async def replay() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await super().handle(scope, replay, private_response)
