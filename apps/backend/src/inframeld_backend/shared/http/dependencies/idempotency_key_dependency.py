from typing import Annotated

from fastapi import Header
from starlette.requests import Request

from inframeld_backend.shared.application.errors.application_errors import InvalidInputError
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey


class IdempotencyKeyDependency:
    """Reject ambiguous headers and convert one key at the HTTP boundary."""

    def __call__(
        self,
        request: Request,
        raw_key: Annotated[
            str,
            Header(
                alias="Idempotency-Key",
                # These document the value object's constraints in OpenAPI.
                # IdempotencyKey performs validation so errors use invalid_input.
                json_schema_extra={
                    "minLength": 1,
                    "maxLength": 128,
                    "pattern": r".*\S.*",
                },
            ),
        ],
    ) -> IdempotencyKey:
        if len(request.headers.getlist("Idempotency-Key")) != 1:
            raise InvalidInputError("Exactly one Idempotency-Key header is required.")

        try:
            return IdempotencyKey(raw_key)
        except ValueError:
            raise InvalidInputError(
                "Idempotency key must be nonblank and at most 128 characters."
            ) from None
