from uuid import UUID

from inframeld_backend.access.application.commands.restore_human_command import RestoreHumanCommand
from inframeld_backend.access.application.commands.suspend_human_command import SuspendHumanCommand
from inframeld_backend.access.application.dtos.human_restoration_result_dto import (
    HumanRestorationResultDTO,
)
from inframeld_backend.access.application.dtos.human_suspension_result_dto import (
    HumanSuspensionResultDTO,
)
from inframeld_backend.access.application.value_objects.security_review_reference import (
    SecurityReviewReference,
)
from inframeld_backend.access.application.value_objects.suspension_reason import SuspensionReason
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.http.requests.human_restoration_request import HumanRestorationRequest
from inframeld_backend.access.http.requests.human_suspension_request import HumanSuspensionRequest
from inframeld_backend.access.http.responses.human_restoration_response import (
    HumanRestorationResponse,
)
from inframeld_backend.access.http.responses.human_suspension_response import (
    HumanSuspensionResponse,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey


class HumanLifecycleMapper:
    @staticmethod
    def suspend_command(
        organization_id: UUID, principal_id: UUID, body: HumanSuspensionRequest
    ) -> SuspendHumanCommand:
        return SuspendHumanCommand(
            OrganizationId(organization_id),
            PrincipalId(principal_id),
            body.expected_access_revision,
            SuspensionReason(body.reason),
        )

    @staticmethod
    def restore_command(
        organization_id: UUID, principal_id: UUID, body: HumanRestorationRequest
    ) -> RestoreHumanCommand:
        return RestoreHumanCommand(
            OrganizationId(organization_id),
            PrincipalId(principal_id),
            body.expected_access_revision,
            SecurityReviewReference(body.security_review_reference),
        )

    @staticmethod
    def suspend_context(
        organization_id: UUID, principal_id: UUID, key: IdempotencyKey
    ) -> IdempotencyContextDTO:
        return IdempotencyContextDTO(
            HttpMethod.POST,
            f"/v1/organizations/{organization_id}/humans/{principal_id}/suspend",
            key,
        )

    @staticmethod
    def restore_context(
        organization_id: UUID, principal_id: UUID, key: IdempotencyKey
    ) -> IdempotencyContextDTO:
        return IdempotencyContextDTO(
            HttpMethod.POST,
            f"/v1/organizations/{organization_id}/humans/{principal_id}/restore",
            key,
        )

    @staticmethod
    def suspension_response(result: HumanSuspensionResultDTO) -> HumanSuspensionResponse:
        return HumanSuspensionResponse(
            operation_id=result.operation.operation_id.value,
            idempotency_expires_at=result.operation.expires_at,
            organization_id=result.organization_id.value,
            principal_id=result.principal_id.value,
            access_revision=result.access_revision,
            access_blocked=True,
            cleanup_operation_id=result.cleanup_operation_id.value,
        )

    @staticmethod
    def restoration_response(result: HumanRestorationResultDTO) -> HumanRestorationResponse:
        return HumanRestorationResponse(
            operation_id=result.operation.operation_id.value,
            idempotency_expires_at=result.operation.expires_at,
            organization_id=result.organization_id.value,
            principal_id=result.principal_id.value,
            access_revision=result.access_revision,
        )
