"""Supply controlled wire outcomes for the registered Processing Profile routers."""

from dataclasses import replace
from datetime import UTC, datetime
from typing import override
from uuid import UUID

from inframeld_backend.access.application.commands.change_processing_profile_grant_command import (
    ChangeProcessingProfileGrantCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.processing_profile_grant_item_dto import (
    ProcessingProfileGrantItemDTO,
)
from inframeld_backend.access.application.dtos.processing_profile_grant_result_dto import (
    ProcessingProfileGrantResultDTO,
)
from inframeld_backend.access.application.dtos.processing_profile_grant_target_dto import (
    ProcessingProfileGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.processing_profile_grants_page_dto import (
    ProcessingProfileGrantsPageDTO,
)
from inframeld_backend.access.application.protocols.processing_profile_grant_changer import (
    ProcessingProfileGrantChanger,
)
from inframeld_backend.access.application.protocols.processing_profile_grants_reader import (
    ProcessingProfileGrantsReader,
)
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.indexing.application.commands.create_processing_profile_command import (
    CreateProcessingProfileCommand,
)
from inframeld_backend.indexing.application.dtos.processing_profile_creation_dto import (
    ProcessingProfileCreationDTO,
)
from inframeld_backend.indexing.application.dtos.processing_profile_dto import ProcessingProfileDTO
from inframeld_backend.indexing.application.dtos.processing_profiles_page_dto import (
    ProcessingProfilesPageDTO,
)
from inframeld_backend.indexing.application.protocols.processing_profile_creator import (
    ProcessingProfileCreator,
)
from inframeld_backend.indexing.application.protocols.processing_profile_reader import (
    ProcessingProfileReader,
)
from inframeld_backend.indexing.domain.enums.processing_profile_action import (
    ProcessingProfileAction,
)
from inframeld_backend.indexing.domain.value_objects.processing_profile_id import (
    ProcessingProfileId,
)
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
from tests.support.processing_profile_scenarios import profile_command

_PROJECT = ProjectId(UUID("00000000-0000-4000-8000-000000000003"))
SDK_PROCESSING_PROFILE_ID = ProcessingProfileId(UUID("00000000-0000-4000-8000-000000000032"))
_ACTOR = PrincipalId(UUID("00000000-0000-4000-8000-000000000001"))
_RECIPIENT = PrincipalId(UUID("00000000-0000-4000-8000-000000000004"))
_UNCHANGED = PrincipalId(UUID("00000000-0000-4000-8000-000000000005"))
_SAMPLE = profile_command(_PROJECT)
_PROFILE = ProcessingProfileDTO(
    project_id=_PROJECT,
    id=SDK_PROCESSING_PROFILE_ID,
    name=_SAMPLE.name,
    display_name=_SAMPLE.display_name,
    definition=_SAMPLE.definition,
)


class MockSDKProcessingProfiles(
    ProcessingProfileCreator,
    ProcessingProfileReader,
    ProcessingProfileGrantChanger,
    ProcessingProfileGrantsReader,
):
    """Populate declared wire responses without simulating SQL or grants."""

    @staticmethod
    def _receipt(name: str) -> CompletedSynchronousOperationDTO:
        return CompletedSynchronousOperationDTO(
            OperationId(name),
            True,
            OperationReplayKind.SAFE_RESULT,
            datetime(2030, 1, 1, tzinfo=UTC),
        )

    @staticmethod
    def _require_actor(access: AccessContextDTO) -> None:
        if access.actor_principal_id != _ACTOR:
            raise AccessDeniedError()

    @override
    async def create(
        self,
        *,
        access: AccessContextDTO,
        command: CreateProcessingProfileCommand,
        context: IdempotencyContextDTO,
    ) -> ProcessingProfileCreationDTO:
        self._require_actor(access)
        if command.project_id != _PROJECT:
            raise ResourceNotFoundError()
        return ProcessingProfileCreationDTO(
            profile=replace(
                _PROFILE,
                name=command.name,
                display_name=command.display_name,
                definition=command.definition,
            ),
            operation=self._receipt("sdk-processing-profile-create"),
            project_access_revision=8,
            initial_actions=tuple(ProcessingProfileAction),
            can_grant=True,
        )

    @override
    async def get(
        self, access: AccessContextDTO, project_id: ProjectId, profile_id: ProcessingProfileId
    ) -> ProcessingProfileDTO:
        self._require_actor(access)
        if project_id != _PROJECT or profile_id != SDK_PROCESSING_PROFILE_ID:
            raise ResourceNotFoundError()
        return _PROFILE

    @override
    async def list_profiles(
        self, access: AccessContextDTO, project_id: ProjectId, limit: int, cursor: str | None
    ) -> ProcessingProfilesPageDTO:
        return ProcessingProfilesPageDTO(
            (await self.get(access, project_id, SDK_PROCESSING_PROFILE_ID),), None
        )

    @override
    async def change(
        self,
        access: AccessContextDTO,
        command: ChangeProcessingProfileGrantCommand,
        context: IdempotencyContextDTO,
    ) -> ProcessingProfileGrantResultDTO:
        await self.get(access, _PROJECT, command.processing_profile_id)
        if command.expected_access_revision != 7:
            raise StaleRevisionError()
        changed = command.recipient_id != _UNCHANGED
        return ProcessingProfileGrantResultDTO(
            target=ProcessingProfileGrantTargetDTO(_PROJECT, SDK_PROCESSING_PROFILE_ID),
            recipient_id=command.recipient_id,
            action=command.action,
            can_grant=command.can_grant,
            access_revision=7 + int(changed),
            changed=changed,
            status_code=201 if command.can_grant is not None and changed else 200,
            operation=self._receipt(f"sdk-processing-profile-grant-{context.method.value.lower()}"),
        )

    @override
    async def list_grants(
        self,
        access: AccessContextDTO,
        profile_id: ProcessingProfileId,
        action: ProcessingProfileAction,
        limit: int,
        cursor: str | None,
    ) -> ProcessingProfileGrantsPageDTO:
        await self.get(access, _PROJECT, profile_id)
        return ProcessingProfileGrantsPageDTO(
            (ProcessingProfileGrantItemDTO(_RECIPIENT, True),), None
        )
