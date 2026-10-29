from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.accepted_async_operation_dto import (
    AcceptedAsyncOperationDTO,
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
from inframeld_backend.shared.application.dtos.unresolved_operation_dto import (
    UnresolvedOperationDTO,
)
from inframeld_backend.shared.application.queries.lookup_original_operation_query import (
    LookupOriginalOperationQuery,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
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
        | AcceptedAsyncOperationDTO
        | InProgressOperationDTO
        | RecoveryRequiredOperationDTO
        | UnresolvedOperationDTO,
    ) -> OperationLookupResponse:
        match result:
            case CompletedSynchronousOperationDTO():
                return CompletedOperationLookupResponse(
                    outcome="completed_synchronous",
                    operationId=result.operation_id.value,
                    classification=result.replay_kind.value,
                    idempotencyExpiresAt=result.expires_at,
                )
            case AcceptedAsyncOperationDTO():
                return AcceptedOperationLookupResponse(
                    outcome="accepted_asynchronous",
                    admission="confirmed",
                    jobReference="unknown",
                    dispatch="not_established",
                    operationId=result.operation_id.value,
                    idempotencyExpiresAt=result.expires_at,
                )
            case InProgressOperationDTO():
                return InProgressOperationLookupResponse(
                    outcome="in_progress", operationId=result.operation_id.value
                )
            case RecoveryRequiredOperationDTO():
                return RecoveryRequiredOperationLookupResponse(
                    outcome="recovery_required",
                    reason="original_outcome_requires_recovery",
                    operationId=result.operation_id.value,
                )
            case UnresolvedOperationDTO():
                return UnresolvedOperationLookupResponse(outcome="unresolved")
