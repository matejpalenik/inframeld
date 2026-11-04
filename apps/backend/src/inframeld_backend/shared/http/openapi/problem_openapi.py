"""Document RFC 9457 responses using FastAPI's generated model components.

FastAPI exposes its response declarations and OpenAPI document as dynamic
mappings. Any and casts are confined to that framework boundary; application
contracts never consume these dictionaries.
"""

from collections.abc import Callable
from functools import partial
from typing import Any, cast

from fastapi import FastAPI
from pydantic import BaseModel
from pydantic.json_schema import JsonSchemaMode

from inframeld_backend.shared.http.definitions.problem_definition import ProblemDefinition
from inframeld_backend.shared.http.responses.problem_details import ProblemDetails

_PROBLEM_RESPONSE_MARKER = "x-inframeld-problem-response"


def _restore_integer_bounds(
    schema: dict[str, Any], model: type[BaseModel], *, mode: JsonSchemaMode
) -> None:
    """Preserve integer constraints rounded by FastAPI's OpenAPI schema model."""
    source = model.model_json_schema(by_alias=True, mode=mode)
    component = schema.get("components", {}).get("schemas", {}).get(model.__name__)
    if not isinstance(component, dict):
        raise ValueError("A configured integer-bound model has no native schema component.")
    component = cast(dict[str, Any], component)

    for name, source_property in source.get("properties", {}).items():
        if source_property.get("type") != "integer":
            continue

        bounds = {
            bound: value
            for bound in ("minimum", "maximum")
            if type(value := source_property.get(bound)) is int
        }
        if not bounds:
            continue

        target = component.get("properties", {}).get(name)
        if not isinstance(target, dict):
            raise ValueError("A configured integer bound has no matching native property.")
        target = cast(dict[str, Any], target)
        if target.get("type") != "integer":
            raise ValueError("A configured integer bound has no matching native property.")

        target.update(bounds)


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
    validation_models: tuple[type[BaseModel], ...],
    serialization_models: tuple[type[BaseModel], ...],
) -> dict[str, Any]:
    """Correct exact model bounds and problem media types after native generation."""
    schema = original_openapi()

    for model in validation_models:
        _restore_integer_bounds(schema, model, mode="validation")
    for model in serialization_models:
        _restore_integer_bounds(schema, model, mode="serialization")

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


def configure_problem_openapi(
    application: FastAPI,
    *,
    validation_models: tuple[type[BaseModel], ...] = (),
    serialization_models: tuple[type[BaseModel], ...] = (),
) -> None:
    """Preserve exact configured bounds and problem media types in native OpenAPI.

    Call once during application construction. The original bound method
    retains access to this application's configuration and schema cache.
    """
    original_openapi = application.openapi
    application.openapi = partial(
        _openapi_with_problem_responses,
        original_openapi,
        validation_models,
        serialization_models,
    )
