from inframeld_backend.shared.application.dtos.retained_deletion_status_dto import (
    RetainedDeletionStatusDTO,
)
from inframeld_backend.shared.application.dtos.unresolved_operation_dto import (
    UnresolvedOperationDTO,
)
from inframeld_backend.shared.application.queries.get_deletion_status_query import (
    GetDeletionStatusQuery,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.http.responses.retained_deletion_status_response import (
    RetainedDeletionStatusResponse,
)
from inframeld_backend.shared.http.responses.unresolved_deletion_status_response import (
    UnresolvedDeletionStatusResponse,
)
from inframeld_backend.shared.http.types.deletion_status_response import DeletionStatusResponse


class DeletionStatusMapper:
    """Convert references and permitted observations without reading or executing work."""

    @staticmethod
    def to_query(operation_id: str) -> GetDeletionStatusQuery:
        return GetDeletionStatusQuery(OperationId(operation_id))

    @staticmethod
    def to_response(
        result: RetainedDeletionStatusDTO | UnresolvedOperationDTO,
    ) -> DeletionStatusResponse:
        match result:
            case RetainedDeletionStatusDTO():
                return RetainedDeletionStatusResponse(
                    outcome="retained",
                    operationId=result.operation_id.value,
                    jobState=result.job_status,
                    admissionConfirmed=result.admission_confirmed,
                    accessBlocked=result.access_blocked,
                    applicationShutdownComplete=result.application_shutdown_complete,
                    physicalCleanupComplete=result.physical_cleanup_complete,
                    retentionExpiresAt=result.expires_at,
                )
            case UnresolvedOperationDTO():
                return UnresolvedDeletionStatusResponse(outcome="unresolved")
