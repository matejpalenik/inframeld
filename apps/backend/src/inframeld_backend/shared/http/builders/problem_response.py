"""Build RFC 9457 HTTP responses from reviewed problem definitions"""

from collections.abc import Mapping

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from inframeld_backend.shared.http.definitions.problem_catalogue import VALIDATION_ERROR_PROBLEM
from inframeld_backend.shared.http.definitions.problem_definition import ProblemDefinition
from inframeld_backend.shared.http.dependencies.request_identity import request_identity
from inframeld_backend.shared.http.responses.problem_details import ProblemDetails
from inframeld_backend.shared.http.responses.validation_issue import ValidationIssue

_ALLOWED_PROTOCOL_HEADERS: frozenset[str] = frozenset({"allow", "retry-after", "www-authenticate"})


def build_problem_response(
    request: Request,
    definition: ProblemDefinition,
    *,
    errors: tuple[ValidationIssue, ...] | None = None,
    protocol_headers: Mapping[str, str] | None = None,
) -> Response:
    "Build a safe HTTP problem response from reviewed server-owned values."

    if definition == VALIDATION_ERROR_PROBLEM and not errors:
        raise ValueError("Validation problems require at least one issue.")

    if definition != VALIDATION_ERROR_PROBLEM and errors is not None:
        raise ValueError("Only validation problems may include validation issues.")

    request_id = request_identity(request)

    problem = ProblemDetails.model_validate(
        {
            "type": definition.type_uri,
            "title": definition.title,
            "status": definition.status,
            "detail": definition.detail,
            "code": definition.code,
            "request_id": request_id.value,
            "errors": errors,
        }
    )

    response_headers = {
        name: value
        for name, value in (protocol_headers or {}).items()
        if name.lower() in _ALLOWED_PROTOCOL_HEADERS
    }

    response_headers.update({"Cache-Control": "no-store", "X-Request-ID": str(problem.request_id)})

    json_response = JSONResponse(
        content=problem.model_dump(mode="json", by_alias=True, exclude_none=True),
        status_code=problem.status,
        headers=response_headers,
        media_type="application/problem+json",
    )

    # If request is HEAD, we return the response without the body.
    if request.method == "HEAD":
        json_response.body = b""

    return json_response
