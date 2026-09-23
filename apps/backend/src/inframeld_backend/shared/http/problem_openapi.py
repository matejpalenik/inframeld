"""Document RFC 9457 responses using FastAPI's generated model components."""

from collections.abc import Callable
from functools import partial
from typing import Any, cast

from fastapi import FastAPI

from inframeld_backend.shared.http.problem_definitions import ProblemDefinition
from inframeld_backend.shared.http.problems import ProblemDetails

_PROBLEM_RESPONSE_MARKER = "x-inframeld-problem-response"


def problem_responses(
    definition: ProblemDefinition,
) -> dict[int | str, dict[str, Any]]:
    """Declare one problem response for a route.

    FastAPI generates the model and its nested components. The OpenAPI hook
    then assigns their reference to the problem media type.
    """
    return {
        definition.status: {
            "description": definition.title,
            "model": ProblemDetails,
            _PROBLEM_RESPONSE_MARKER: True,
        }
    }


def _openapi_with_problem_responses(
    original_openapi: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    """Generate the native schema and correct marked problem media types."""
    schema = original_openapi()

    for path_item in schema.get("paths", {}).values():
        for operation_value in path_item.values():
            if not isinstance(operation_value, dict):
                continue

            operation = cast(dict[str, Any], operation_value)

            for response in operation.get("responses", {}).values():
                if response.get(_PROBLEM_RESPONSE_MARKER) is not True:
                    continue

                content = response["content"]

                if len(content) != 1:
                    raise ValueError("A declared problem response must have one representation.")

                # Preserve FastAPI's generated schema and component reference.
                representation = next(iter(content.values()))
                response["content"] = {
                    "application/problem+json": representation,
                }
                del response[_PROBLEM_RESPONSE_MARKER]

    return schema


def configure_problem_openapi(application: FastAPI) -> None:
    """Install problem media-type correction while preserving native generation.

    Call once during application construction. The original bound method
    retains access to this application's configuration and schema cache.
    """
    original_openapi = application.openapi
    application.openapi = partial(
        _openapi_with_problem_responses,
        original_openapi,
    )
