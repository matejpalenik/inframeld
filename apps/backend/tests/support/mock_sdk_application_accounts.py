"""Supply account wire outcomes without simulating database or credential lifecycle work."""

from datetime import UTC, datetime, timedelta
from typing import override
from uuid import UUID

from inframeld_backend.access.application.commands.create_application_account_command import (
    CreateApplicationAccountCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_account_creation_result_dto import (
    ApplicationAccountCreationResultDTO,
)
from inframeld_backend.access.application.dtos.application_account_metadata_dto import (
    ApplicationAccountMetadataDTO,
)
from inframeld_backend.access.application.dtos.application_key_metadata_dto import (
    ApplicationKeyMetadataDTO,
)
from inframeld_backend.access.application.dtos.application_keys_page_dto import (
    ApplicationKeysPageDTO,
)
from inframeld_backend.access.application.dtos.created_application_account_dto import (
    CreatedApplicationAccountDTO,
)
from inframeld_backend.access.application.protocols.application_account_creator import (
    ApplicationAccountCreator,
)
from inframeld_backend.access.application.protocols.application_account_reader import (
    ApplicationAccountReader,
)
from inframeld_backend.access.application.queries.list_application_keys_query import (
    ListApplicationKeysQuery,
)
from inframeld_backend.access.domain.enums.application_key_adapter import ApplicationKeyAdapter
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
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
    ConflictError,
    InvalidInputError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName

_PROJECT = ProjectId(UUID("00000000-0000-4000-8000-000000000003"))
_APP = PrincipalId(UUID("00000000-0000-4000-8000-000000000008"))
_EXISTING = PrincipalId(UUID("00000000-0000-4000-8000-000000000009"))
_NOW = datetime(2030, 1, 1, tzinfo=UTC)


class MockSDKApplicationAccounts(ApplicationAccountCreator, ApplicationAccountReader):
    @override
    async def create(
        self,
        *,
        access: AccessContextDTO,
        command: CreateApplicationAccountCommand,
        context: IdempotencyContextDTO,
    ) -> ApplicationAccountCreationResultDTO:
        if command.project_id != _PROJECT:
            raise ResourceNotFoundError()
        if command.expected_access_revision == 9007199254740991:
            raise ConflictError("The controlled Project revision is exhausted.")
        operation = CompletedSynchronousOperationDTO(
            OperationId("sdk-application-account-create"),
            True,
            OperationReplayKind.SAFE_RESULT,
            _NOW,
        )
        return ApplicationAccountCreationResultDTO(
            CreatedApplicationAccountDTO(
                operation.operation_id,
                OrganizationId(UUID("00000000-0000-4000-8000-000000000002")),
                _PROJECT,
                _APP,
                access.actor_principal_id,
                command.name,
                command.display_name.value,
                command.expected_access_revision + 1,
                tuple(
                    ActionId(value)
                    for value in (
                        "issue-application-keys",
                        "revoke-application-keys",
                        "delete-application-account",
                    )
                ),
            ),
            operation,
        )

    @override
    async def get_account(
        self, *, access: AccessContextDTO, project_id: ProjectId, principal_id: PrincipalId
    ) -> ApplicationAccountMetadataDTO:
        if project_id != _PROJECT or principal_id not in (_APP, _EXISTING):
            raise ResourceNotFoundError()
        return ApplicationAccountMetadataDTO(
            OrganizationId(UUID("00000000-0000-4000-8000-000000000002")),
            project_id,
            principal_id,
            ResourceName("support-bot" if principal_id == _APP else "existing-bot"),
            "SupportBot" if principal_id == _APP else "ExistingBot",
            PrincipalStatus.ACTIVE,
            _NOW,
            8,
        )

    @override
    async def resolve_account(
        self, *, access: AccessContextDTO, project_id: ProjectId, name: ResourceName
    ) -> ApplicationAccountMetadataDTO:
        if name.value not in ("support-bot", "existing-bot"):
            raise ResourceNotFoundError()
        return await self.get_account(
            access=access,
            project_id=project_id,
            principal_id=_APP if name.value == "support-bot" else _EXISTING,
        )

    @override
    async def list_keys(
        self, *, access: AccessContextDTO, query: ListApplicationKeysQuery
    ) -> ApplicationKeysPageDTO:
        await self.get_account(
            access=access, project_id=query.project_id, principal_id=query.application_principal_id
        )
        if query.cursor not in (None, "Y29udGludWU"):
            raise InvalidInputError()
        if query.application_principal_id == _APP:
            return ApplicationKeysPageDTO((), None)
        keys = (self._key(10), self._key(11))
        if query.cursor is not None:
            return ApplicationKeysPageDTO(keys[1:], None)
        return ApplicationKeysPageDTO(
            keys[: query.limit], "Y29udGludWU" if query.limit == 1 else None
        )

    @override
    async def get_key(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        application_principal_id: PrincipalId,
        key_id: ApplicationKeyId,
    ) -> ApplicationKeyMetadataDTO:
        await self.get_account(
            access=access, project_id=project_id, principal_id=application_principal_id
        )
        for key in (self._key(10), self._key(11)):
            if application_principal_id == _EXISTING and key.key_id == key_id:
                return key
        raise ResourceNotFoundError()

    @staticmethod
    def _key(number: int) -> ApplicationKeyMetadataDTO:
        return ApplicationKeyMetadataDTO(
            ApplicationKeyId(UUID(f"00000000-0000-4000-8000-{number:012d}")),
            _EXISTING,
            _PROJECT,
            (ApplicationKeyAdapter.HTTP, ApplicationKeyAdapter.MCP),
            _NOW,
            _NOW + timedelta(days=90),
            None,
        )
