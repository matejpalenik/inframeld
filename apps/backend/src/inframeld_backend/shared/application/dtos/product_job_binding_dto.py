from dataclasses import dataclass

from inframeld_backend.access.application.dtos.admitted_work_authority_dto import (
    AdmittedWorkAuthorityDTO,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_id import RequestId


@dataclass(frozen=True, slots=True)
class ProductJobBindingDTO:
    """Keep product replay and current-principal authority together."""

    operation_id: OperationId
    request_id: RequestId
    authority: AdmittedWorkAuthorityDTO
