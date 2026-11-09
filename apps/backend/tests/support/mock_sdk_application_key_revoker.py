"""Supply safe wire outcomes without simulating SQL, retirement or current authority."""

from datetime import UTC, datetime, timedelta
from typing import override
from uuid import UUID

from inframeld_backend.access.application.commands.revoke_application_key_command import (
    RevokeApplicationKeyCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_key_authentication_dto import (
    ApplicationKeyAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.application_key_metadata_dto import (
    ApplicationKeyMetadataDTO,
)
from inframeld_backend.access.application.dtos.application_key_revocation_record_dto import (
    ApplicationKeyRevocationRecordDTO,
)
from inframeld_backend.access.application.dtos.application_key_revocation_result_dto import (
    ApplicationKeyRevocationResultDTO,
)
from inframeld_backend.access.application.protocols.application_key_revoker import (
    ApplicationKeyRevoker,
)
from inframeld_backend.access.domain.enums.application_key_adapter import ApplicationKeyAdapter
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
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

_PROJECT = ProjectId(UUID("00000000-0000-4000-8000-000000000003"))
_APPLICATION = PrincipalId(UUID("00000000-0000-4000-8000-000000000008"))
_KEY = ApplicationKeyId(UUID("00000000-0000-4000-8000-000000000010"))
_NOW = datetime(2030, 1, 1, tzinfo=UTC)


class MockSDKApplicationKeyRevoker(ApplicationKeyRevoker):
    @override
    async def revoke(
        self,
        *,
        access: AccessContextDTO,
        command: RevokeApplicationKeyCommand,
        context: IdempotencyContextDTO,
    ) -> ApplicationKeyRevocationResultDTO:
        if isinstance(access.authentication_evidence, ApplicationKeyAuthenticationDTO):
            raise AccessDeniedError()
        if (
            command.project_id != _PROJECT
            or command.application_principal_id != _APPLICATION
            or command.key_id != _KEY
        ):
            raise ResourceNotFoundError()
        noop = context.key.value == "sdk-revoke-noop"
        if command.expected_access_revision not in (
            (8,) if noop else (7, RevisionValidation.MAX_VALUE - 1)
        ):
            raise StaleRevisionError()
        operation = CompletedSynchronousOperationDTO(
            OperationId(
                "sdk-application-key-revoke-noop" if noop else "sdk-application-key-revoke"
            ),
            context.key.value != "sdk-revoke-replay",
            OperationReplayKind.SAFE_RESULT,
            _NOW + timedelta(days=1),
        )
        return ApplicationKeyRevocationResultDTO(
            original=ApplicationKeyRevocationRecordDTO(
                operation_id=operation.operation_id,
                organization_id=OrganizationId(UUID(int=2)),
                installation_id=InstallationId(UUID(int=1)),
                actor_principal_id=access.actor_principal_id,
                access_revision=command.expected_access_revision + (0 if noop else 1),
                metadata=ApplicationKeyMetadataDTO(
                    key_id=_KEY,
                    application_principal_id=_APPLICATION,
                    project_id=_PROJECT,
                    allowed_adapters=(ApplicationKeyAdapter.HTTP, ApplicationKeyAdapter.MCP),
                    created_at=_NOW - timedelta(days=1),
                    expires_at=_NOW + timedelta(days=89),
                    revoked_at=_NOW,
                ),
            ),
            operation=operation,
        )
