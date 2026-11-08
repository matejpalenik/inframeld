"""Supply first/replay wire alternatives, without simulating SQL or issuance authority."""

from datetime import UTC, datetime, timedelta
from typing import override
from uuid import UUID

from inframeld_backend.access.application.commands.issue_application_key_command import (
    IssueApplicationKeyCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_key_authentication_dto import (
    ApplicationKeyAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.application_key_issuance_record_dto import (
    ApplicationKeyIssuanceRecordDTO,
)
from inframeld_backend.access.application.dtos.application_key_issue_result_dto import (
    ApplicationKeyIssueResultDTO,
)
from inframeld_backend.access.application.dtos.application_key_metadata_dto import (
    ApplicationKeyMetadataDTO,
)
from inframeld_backend.access.application.protocols.application_key_issuer import (
    ApplicationKeyIssuer,
)
from inframeld_backend.access.application.value_objects.application_key_credential import (
    ApplicationKeyCredential,
)
from inframeld_backend.access.domain.value_objects.application_key_id import ApplicationKeyId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ResourceNotFoundError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

_PROJECT = ProjectId(UUID("00000000-0000-4000-8000-000000000003"))
_APPLICATION = PrincipalId(UUID("00000000-0000-4000-8000-000000000008"))
_CREDENTIAL = ApplicationKeyCredential("ifm_app_00000000-0000-4000-8000-000000000010_" + "A" * 43)
_NOW = datetime(2030, 1, 1, tzinfo=UTC)


class MockSDKApplicationKeyIssuer(ApplicationKeyIssuer):
    @override
    async def issue(
        self,
        *,
        access: AccessContextDTO,
        command: IssueApplicationKeyCommand,
        context: IdempotencyContextDTO,
    ) -> ApplicationKeyIssueResultDTO:
        if isinstance(access.authentication_evidence, ApplicationKeyAuthenticationDTO):
            raise AccessDeniedError()
        if command.project_id != _PROJECT or command.application_principal_id != _APPLICATION:
            raise ResourceNotFoundError()
        if command.expected_access_revision not in (7, 9007199254740990):
            raise StaleRevisionError()
        replay = context.key.value == "sdk-key-replay"
        operation = CompletedSynchronousOperationDTO(
            OperationId("sdk-application-key-issue"),
            not replay,
            OperationReplayKind.ISSUED_SECRET,
            _NOW,
        )
        return ApplicationKeyIssueResultDTO(
            original=ApplicationKeyIssuanceRecordDTO(
                operation_id=operation.operation_id,
                organization_id=OrganizationId(UUID(int=2)),
                installation_id=InstallationId(UUID(int=1)),
                issuer_principal_id=access.actor_principal_id,
                access_revision=command.expected_access_revision + 1,
                metadata=ApplicationKeyMetadataDTO(
                    key_id=ApplicationKeyId(_CREDENTIAL.key_id.value),
                    application_principal_id=_APPLICATION,
                    project_id=_PROJECT,
                    allowed_adapters=command.allowed_adapters,
                    created_at=_NOW,
                    expires_at=_NOW + timedelta(seconds=command.expires_in_seconds or 7776000),
                    revoked_at=None,
                ),
            ),
            operation=operation,
            credential=None if replay else _CREDENTIAL,
        )
