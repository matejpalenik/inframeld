from dataclasses import dataclass

from inframeld_backend.shared.application.errors.application_errors import InvalidInputError
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


@dataclass(frozen=True, slots=True)
class GetDeletionStatusQuery:
    """Request a bounded retained observation without supplying an actor or Project."""

    operation_id: OperationId

    def __post_init__(self) -> None:
        if len(self.operation_id.value) > 128:
            raise InvalidInputError()
