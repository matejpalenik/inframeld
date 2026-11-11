"""Supply typed wire outcomes without simulating persistence or current management."""

from datetime import UTC, datetime, timedelta
from typing import override
from uuid import UUID

from inframeld_backend.access.application.commands.set_project_upload_default_command import (
    SetProjectUploadDefaultCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_key_authentication_dto import (
    ApplicationKeyAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.project_upload_default_change_result_dto import (
    ProjectUploadDefaultChangeResultDTO,
)
from inframeld_backend.access.application.dtos.project_upload_default_dto import (
    ProjectUploadDefaultDTO,
)
from inframeld_backend.access.application.protocols.project_upload_default_changer import (
    ProjectUploadDefaultChanger,
)
from inframeld_backend.access.application.protocols.project_upload_default_reader import (
    ProjectUploadDefaultReader,
)
from inframeld_backend.access.application.queries.get_project_upload_default_query import (
    GetProjectUploadDefaultQuery,
)
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.domain.value_objects.upload_audience import UploadAudience
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    DependencyUnavailableError,
    ResourceNotFoundError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation

_PROJECT = ProjectId(UUID("00000000-0000-4000-8000-000000000003"))
_UNSET = ProjectId(UUID("00000000-0000-4000-8000-000000000005"))
_ORGANIZATION = OrganizationId(UUID("00000000-0000-4000-8000-000000000002"))
_GROUPS = tuple(
    AccessGroupId(UUID("00000000-0000-4000-8000-" + f"{number:012}")) for number in (10, 20, 30)
)
_NOW = datetime(2030, 1, 1, tzinfo=UTC)


class MockSDKProjectUploadDefaults(ProjectUploadDefaultReader, ProjectUploadDefaultChanger):
    @override
    async def get(
        self, *, access: AccessContextDTO, query: GetProjectUploadDefaultQuery
    ) -> ProjectUploadDefaultDTO:
        if isinstance(access.authentication_evidence, ApplicationKeyAuthenticationDTO):
            raise AccessDeniedError()
        if query.project_id not in (_PROJECT, _UNSET):
            raise ResourceNotFoundError()
        return ProjectUploadDefaultDTO(
            _ORGANIZATION,
            query.project_id,
            7 if query.project_id == _UNSET else 9,
            None if query.project_id == _UNSET else UploadAudience((_GROUPS[2],)),
        )

    @override
    async def set(
        self,
        *,
        access: AccessContextDTO,
        command: SetProjectUploadDefaultCommand,
        context: IdempotencyContextDTO,
    ) -> ProjectUploadDefaultChangeResultDTO:
        if isinstance(access.authentication_evidence, ApplicationKeyAuthenticationDTO):
            raise AccessDeniedError()
        if command.project_id != _PROJECT or any(
            group not in _GROUPS for group in command.audience.group_ids
        ):
            raise ResourceNotFoundError()
        key = context.key.value
        if key in {"sdk-upload-denied-old", "sdk-upload-denied-new", "sdk-upload-denied-retained"}:
            raise AccessDeniedError()
        if key == "sdk-upload-expired":
            raise ConflictError("The original upload-default result is unavailable.")
        if key == "sdk-upload-unknown":
            raise DependencyUnavailableError()
        noop = key == "sdk-upload-noop"
        if command.expected_access_revision not in (
            (9,) if noop else (7, RevisionValidation.MAX_VALUE - 1)
        ):
            raise StaleRevisionError()
        if noop and command.audience != UploadAudience((_GROUPS[2],)):
            raise ConflictError()
        return ProjectUploadDefaultChangeResultDTO(
            ProjectUploadDefaultDTO(
                _ORGANIZATION,
                _PROJECT,
                command.expected_access_revision + (0 if noop else 1),
                command.audience,
            ),
            CompletedSynchronousOperationDTO(
                OperationId("sdk-upload-noop" if noop else "sdk-upload-original"),
                key != "sdk-upload-replay",
                OperationReplayKind.SAFE_RESULT,
                _NOW + timedelta(days=1),
            ),
        )
