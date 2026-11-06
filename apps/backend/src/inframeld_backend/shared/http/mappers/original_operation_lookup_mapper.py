from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.accepted_operation_lookup_dto import (
    AcceptedOperationLookupDTO,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.in_progress_operation_dto import (
    InProgressOperationDTO,
)
from inframeld_backend.shared.application.dtos.recovery_required_operation_dto import (
    RecoveryRequiredOperationDTO,
)
from inframeld_backend.shared.application.dtos.retained_deletion_status_dto import (
    RetainedDeletionStatusDTO,
)
from inframeld_backend.shared.application.dtos.unresolved_operation_dto import (
    UnresolvedOperationDTO,
)
from inframeld_backend.shared.application.enums.operation_lookup_outcome import (
    OperationLookupOutcome,
)
from inframeld_backend.shared.application.queries.lookup_original_operation_query import (
    LookupOriginalOperationQuery,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.http.enums.operation_admission_confirmation import (
    OperationAdmissionConfirmation,
)
from inframeld_backend.shared.http.enums.operation_dispatch_establishment import (
    OperationDispatchEstablishment,
)
from inframeld_backend.shared.http.enums.operation_recovery_reason import OperationRecoveryReason
from inframeld_backend.shared.http.enums.unknown_job_reference import UnknownJobReference
from inframeld_backend.shared.http.mappers.deletion_status_mapper import DeletionStatusMapper
from inframeld_backend.shared.http.requests.original_operation_lookup_request import (
    OriginalOperationLookupRequest,
)
from inframeld_backend.shared.http.responses.accepted_operation_lookup_response import (
    AcceptedOperationLookupResponse,
)
from inframeld_backend.shared.http.responses.completed_operation_lookup_response import (
    CompletedOperationLookupResponse,
)
from inframeld_backend.shared.http.responses.in_progress_operation_lookup_response import (
    InProgressOperationLookupResponse,
)
from inframeld_backend.shared.http.responses.known_job_reference_response import (
    KnownJobReferenceResponse,
)
from inframeld_backend.shared.http.responses.recovery_required_operation_lookup_response import (
    RecoveryRequiredOperationLookupResponse,
)
from inframeld_backend.shared.http.responses.unresolved_operation_lookup_response import (
    UnresolvedOperationLookupResponse,
)
from inframeld_backend.shared.http.types.operation_lookup_response import OperationLookupResponse


class OriginalOperationLookupMapper:
    """Convert lookup input and permitted outcomes without reading or executing work."""

    @staticmethod
    def to_query(body: OriginalOperationLookupRequest) -> LookupOriginalOperationQuery:
        return LookupOriginalOperationQuery(
            installation_id=InstallationId(body.installation_id),
            organization_id=OrganizationId(body.organization_id),
            project_id=ProjectId(body.project_id) if body.project_id is not None else None,
            method=body.method,
            requested_route=body.requested_route,
            key=IdempotencyKey(body.key),
            expected_authority=OperationLookupAuthority(
                body.expected_authority.family, ActionId(body.expected_authority.action_id)
            ),
        )

    @staticmethod
    def to_response(
        result: CompletedSynchronousOperationDTO
        | AcceptedOperationLookupDTO
        | InProgressOperationDTO
        | RecoveryRequiredOperationDTO
        | RetainedDeletionStatusDTO
        | UnresolvedOperationDTO,
    ) -> OperationLookupResponse:
        match result:
            case RetainedDeletionStatusDTO():
                return DeletionStatusMapper.to_response(result)
            case CompletedSynchronousOperationDTO():
                return CompletedOperationLookupResponse(
                    outcome=OperationLookupOutcome.COMPLETED_SYNCHRONOUS,
                    operationId=result.operation_id.value,
                    classification=result.replay_kind,
                    idempotencyExpiresAt=result.expires_at,
                )
            case AcceptedOperationLookupDTO():
                return AcceptedOperationLookupResponse(
                    outcome=OperationLookupOutcome.ACCEPTED_ASYNCHRONOUS,
                    admission=OperationAdmissionConfirmation.CONFIRMED,
                    jobReference=KnownJobReferenceResponse(jobId=result.job_id.value)
                    if result.job_id is not None
                    else UnknownJobReference.UNKNOWN,
                    dispatch=OperationDispatchEstablishment.NOT_ESTABLISHED,
                    operationId=result.operation_id.value,
                    idempotencyExpiresAt=result.expires_at,
                )
            case InProgressOperationDTO():
                return InProgressOperationLookupResponse(
                    outcome=OperationLookupOutcome.IN_PROGRESS,
                    operationId=result.operation_id.value,
                )
            case RecoveryRequiredOperationDTO():
                return RecoveryRequiredOperationLookupResponse(
                    outcome=OperationLookupOutcome.RECOVERY_REQUIRED,
                    reason=OperationRecoveryReason.ORIGINAL_OUTCOME_REQUIRES_RECOVERY,
                    operationId=result.operation_id.value,
                )
            case UnresolvedOperationDTO():
                return UnresolvedOperationLookupResponse(outcome=OperationLookupOutcome.UNRESOLVED)
