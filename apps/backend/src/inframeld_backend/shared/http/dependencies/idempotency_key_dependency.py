from typing import Annotated

from fastapi import Header
from starlette.requests import Request

from inframeld_backend.shared.application.errors.application_errors import InvalidInputError
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey


class IdempotencyKeyDependency:
    def __call__(
        self, request: Request, raw_key: Annotated[str, Header(alias="Idempotency-Key")]
    ) -> IdempotencyKey:
        if len(request.headers.getlist("Idempotency-Key")) != 1:
            raise InvalidInputError("Exactly one Idempotency-Key header is required.")

        try:
            return IdempotencyKey(raw_key)
        except ValueError:
            raise InvalidInputError(
                "Idempotency key must be nonblank and at most 128 characters."
            ) from None
