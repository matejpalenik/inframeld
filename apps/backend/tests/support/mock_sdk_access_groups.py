"""Supply group wire outcomes without simulating database mutations or authority policy."""

from datetime import UTC, datetime
from typing import override
from uuid import UUID

from inframeld_backend.access.application.commands.change_access_group_relationship_command import (
    ChangeAccessGroupRelationshipCommand,
)
from inframeld_backend.access.application.commands.create_access_group_command import (
    CreateAccessGroupCommand,
)
from inframeld_backend.access.application.commands.delete_access_group_command import (
    DeleteAccessGroupCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.access_group_creation_result_dto import (
    AccessGroupCreationResultDTO,
)
from inframeld_backend.access.application.dtos.access_group_deletion_result_dto import (
    AccessGroupDeletionResultDTO,
)
from inframeld_backend.access.application.dtos.access_group_metadata_dto import (
    AccessGroupMetadataDTO,
)
from inframeld_backend.access.application.dtos.access_group_principal_dto import (
    AccessGroupPrincipalDTO,
)
from inframeld_backend.access.application.dtos.access_group_principals_page_dto import (
    AccessGroupPrincipalsPageDTO,
)
from inframeld_backend.access.application.dtos.access_group_relationship_result_dto import (
    AccessGroupRelationshipResultDTO,
)
from inframeld_backend.access.application.dtos.created_access_group_dto import CreatedAccessGroupDTO
from inframeld_backend.access.application.dtos.deleted_access_group_dto import DeletedAccessGroupDTO
from inframeld_backend.access.application.enums.access_group_change_kind import (
    AccessGroupChangeKind,
)
from inframeld_backend.access.application.enums.access_group_collection import AccessGroupCollection
from inframeld_backend.access.application.protocols.access_group_creator import AccessGroupCreator
from inframeld_backend.access.application.protocols.access_group_deleter import AccessGroupDeleter
from inframeld_backend.access.application.protocols.access_group_reader import AccessGroupReader
from inframeld_backend.access.application.protocols.access_group_relationship_changer import (
    AccessGroupRelationshipChanger,
)
from inframeld_backend.access.application.queries.list_access_group_principals_query import (
    ListAccessGroupPrincipalsQuery,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.access_group_relationships import (
    AccessGroupRelationships,
)
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
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName

_PROJECT = ProjectId(UUID("00000000-0000-4000-8000-000000000003"))
_GROUP = AccessGroupId(UUID("00000000-0000-4000-8000-000000000007"))
_LEGACY = AccessGroupId(UUID("00000000-0000-4000-8000-000000000005"))
_ORGANIZATION = OrganizationId(UUID("00000000-0000-4000-8000-000000000002"))
_NOW = datetime(2030, 1, 1, tzinfo=UTC)


class MockSDKAccessGroups(
    AccessGroupCreator, AccessGroupReader, AccessGroupRelationshipChanger, AccessGroupDeleter
):
    @override
    async def create(
        self,
        *,
        access: AccessContextDTO,
        command: CreateAccessGroupCommand,
        context: IdempotencyContextDTO,
    ) -> AccessGroupCreationResultDTO:
        if command.project_id != _PROJECT:
            raise ResourceNotFoundError()
        if command.expected_access_revision == RevisionValidation.MAX_VALUE:
            raise ConflictError("The controlled Project revision is exhausted.")
        operation = self._operation("create")
        return AccessGroupCreationResultDTO(
            CreatedAccessGroupDTO(
                operation.operation_id,
                _ORGANIZATION,
                _PROJECT,
                _GROUP,
                access.actor_principal_id,
                command.name,
                command.display_name.value,
                command.expected_access_revision + 1,
            ),
            operation,
        )

    @override
    async def inspect(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        selector: AccessGroupId | ResourceName,
    ) -> AccessGroupMetadataDTO:
        if project_id != _PROJECT or selector not in (
            _GROUP,
            _LEGACY,
            ResourceName("support-knowledge"),
        ):
            raise ResourceNotFoundError()
        legacy = selector == _LEGACY
        return AccessGroupMetadataDTO(
            _ORGANIZATION,
            _PROJECT,
            _LEGACY if legacy else _GROUP,
            None if legacy else ResourceName("support-knowledge"),
            "ExistingGroup" if legacy else "SupportKnowledge",
            _NOW,
            8,
        )

    @override
    async def list_principals(
        self, *, access: AccessContextDTO, query: ListAccessGroupPrincipalsQuery
    ) -> AccessGroupPrincipalsPageDTO:
        await self.inspect(access=access, project_id=query.project_id, selector=query.group_id)
        if query.cursor not in (None, "Y29udGludWU"):
            raise InvalidInputError()
        items = (
            AccessGroupPrincipalDTO(
                PrincipalId(UUID("00000000-0000-4000-8000-000000000001")),
                PrincipalKind.HUMAN,
                "Alice",
            ),
        )
        if query.collection is AccessGroupCollection.MEMBERS:
            items += (
                AccessGroupPrincipalDTO(
                    PrincipalId(UUID("00000000-0000-4000-8000-000000000008")),
                    PrincipalKind.APPLICATION,
                    "SupportBot",
                ),
            )
        if query.cursor is not None:
            items = items[1:]
        return AccessGroupPrincipalsPageDTO(
            _PROJECT,
            query.group_id,
            8,
            items[: query.limit],
            "Y29udGludWU" if len(items) > query.limit else None,
        )

    @override
    async def change(
        self,
        *,
        access: AccessContextDTO,
        command: ChangeAccessGroupRelationshipCommand,
        context: IdempotencyContextDTO,
    ) -> AccessGroupRelationshipResultDTO:
        await self.inspect(access=access, project_id=command.project_id, selector=command.group_id)
        if command.change_kind is AccessGroupChangeKind.APPOINT_MANAGER and str(
            command.principal_id.value
        ).endswith("000000000008"):
            raise InvalidInputError("Applications cannot manage access groups.")
        changed = context.key.value != "sdk-group-noop"
        kind = command.change_kind
        after = AccessGroupRelationships(
            kind is not AccessGroupChangeKind.REMOVE_MEMBER,
            kind is AccessGroupChangeKind.APPOINT_MANAGER,
        )
        return AccessGroupRelationshipResultDTO(
            _ORGANIZATION,
            _PROJECT,
            _GROUP,
            access.actor_principal_id,
            command.principal_id,
            kind,
            command.expected_access_revision + int(changed),
            changed,
            after,
            kind.success_status(changed=changed),
            self._operation(kind.value),
        )

    @override
    async def delete(
        self,
        *,
        access: AccessContextDTO,
        command: DeleteAccessGroupCommand,
        context: IdempotencyContextDTO,
        request_id: RequestId,
    ) -> AccessGroupDeletionResultDTO:
        await self.inspect(access=access, project_id=command.project_id, selector=command.group_id)
        operation = self._operation("delete")
        return AccessGroupDeletionResultDTO(
            DeletedAccessGroupDTO(
                operation.operation_id,
                _ORGANIZATION,
                _PROJECT,
                _GROUP,
                access.actor_principal_id,
                command.expected_access_revision + 1,
            ),
            operation,
        )

    @staticmethod
    def _operation(kind: str) -> CompletedSynchronousOperationDTO:
        return CompletedSynchronousOperationDTO(
            OperationId("sdk-group-" + kind), True, OperationReplayKind.SAFE_RESULT, _NOW
        )
