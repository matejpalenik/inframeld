from dataclasses import dataclass

from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_id import RequestId


@dataclass(frozen=True, slots=True)
class BusinessOperationArtifactOriginDTO:
    """Retain original business attribution without making it cleanup execution identity."""

    operation_id: OperationId
    request_id: RequestId
