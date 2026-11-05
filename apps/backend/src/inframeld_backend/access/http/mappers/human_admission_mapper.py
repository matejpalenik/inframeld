from uuid import UUID

from inframeld_backend.access.application.commands.admit_human_command import AdmitHumanCommand
from inframeld_backend.access.application.dtos.human_admission_result_dto import (
    HumanAdmissionResultDTO,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.http.requests.human_admission_request import HumanAdmissionRequest
from inframeld_backend.access.http.responses.human_admission_response import HumanAdmissionResponse
from inframeld_backend.shared.application.dtos.idempotency_context_dto import (
    IdempotencyContextDTO,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey


class HumanAdmissionMapper:
    @staticmethod
    def command(organization_id: UUID, body: HumanAdmissionRequest) -> AdmitHumanCommand:
        return AdmitHumanCommand(
            OrganizationId(organization_id), body.identity_id, body.expected_access_revision
        )

    @staticmethod
    def context(organization_id: UUID, key: IdempotencyKey) -> IdempotencyContextDTO:
        return IdempotencyContextDTO(
            HttpMethod.POST, f"/v1/organizations/{organization_id}/human-admissions", key
        )

    @staticmethod
    def response(result: HumanAdmissionResultDTO) -> HumanAdmissionResponse:
        return HumanAdmissionResponse(
            operation_id=result.operation.operation_id.value,
            idempotency_expires_at=result.operation.expires_at,
            organization_id=result.organization_id.value,
            principal_id=result.principal_id.value,
            access_revision=result.access_revision,
            changed=result.changed,
        )
