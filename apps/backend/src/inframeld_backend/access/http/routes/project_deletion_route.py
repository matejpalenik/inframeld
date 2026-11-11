from typing import override

from fastapi.routing import APIRoute
from starlette.requests import Request
from starlette.types import Message, Receive, Scope, Send

from inframeld_backend.shared.http.builders.problem_response import build_problem_response
from inframeld_backend.shared.http.definitions.problem_catalogue import INVALID_INPUT_PROBLEM


class ProjectDeletionRoute(APIRoute):
    """Keep bodyless deletion unambiguous and every response private."""

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
