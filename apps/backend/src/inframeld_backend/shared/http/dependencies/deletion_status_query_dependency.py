from typing import Annotated

from fastapi import Query
from starlette.requests import Request

from inframeld_backend.shared.application.errors.application_errors import InvalidInputError
from inframeld_backend.shared.application.queries.get_deletion_status_query import (
    GetDeletionStatusQuery,
)
from inframeld_backend.shared.http.mappers.deletion_status_mapper import DeletionStatusMapper


class DeletionStatusQueryDependency:
    """Extract one opaque original reference without accepting caller-selected scope."""

    def __call__(
        self,
        request: Request,
        operation_id: Annotated[str, Query(alias="operationId", min_length=1, max_length=128)],
    ) -> GetDeletionStatusQuery:
        if (
            set(request.query_params) != {"operationId"}
            or len(request.query_params.getlist("operationId")) != 1
        ):
            raise InvalidInputError()

        try:
            return DeletionStatusMapper.to_query(operation_id)
        except (TypeError, ValueError):
            raise InvalidInputError() from None
