from datetime import datetime
from typing import TypedDict
from uuid import UUID

from inframeld_backend.access.application.dtos.access_group_creation_result_dto import (
    AccessGroupCreationResultDTO,
)
from inframeld_backend.access.application.dtos.access_group_deletion_result_dto import (
    AccessGroupDeletionResultDTO,
)
from inframeld_backend.access.application.dtos.access_group_metadata_dto import (
    AccessGroupMetadataDTO,
)
from inframeld_backend.access.application.dtos.access_group_principals_page_dto import (
    AccessGroupPrincipalsPageDTO,
)
from inframeld_backend.access.application.dtos.access_group_relationship_result_dto import (
    AccessGroupRelationshipResultDTO,
)
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.responses.access_group_creation_response import (
    AccessGroupCreationResponse,
)
from inframeld_backend.access.http.responses.access_group_deletion_response import (
    AccessGroupDeletionResponse,
)
from inframeld_backend.access.http.responses.access_group_manager_removal_response import (
    AccessGroupManagerRemovalResponse,
)
from inframeld_backend.access.http.responses.access_group_manager_response import (
    AccessGroupManagerResponse,
)
from inframeld_backend.access.http.responses.access_group_membership_removal_response import (
    AccessGroupMembershipRemovalResponse,
)
from inframeld_backend.access.http.responses.access_group_membership_response import (
    AccessGroupMembershipResponse,
)
from inframeld_backend.access.http.responses.access_group_metadata_response import (
    AccessGroupMetadataResponse,
)
from inframeld_backend.access.http.responses.access_group_principal_response import (
    AccessGroupPrincipalResponse,
)
from inframeld_backend.access.http.responses.access_group_principals_page_response import (
    AccessGroupPrincipalsPageResponse,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)


class _MutationFields(TypedDict):
    operation_id: str
    idempotency_expires_at: datetime
    project_id: UUID
    access_group_id: UUID
    access_revision: int


class AccessGroupMapper:
    @staticmethod
    def _fields(
        operation: CompletedSynchronousOperationDTO,
        project: ProjectId,
        group: AccessGroupId,
        revision: int,
    ) -> _MutationFields:
        return {
            "operation_id": operation.operation_id.value,
            "idempotency_expires_at": operation.expires_at,
            "project_id": project.value,
            "access_group_id": group.value,
            "access_revision": revision,
        }

    @staticmethod
    def creation(result: AccessGroupCreationResultDTO) -> AccessGroupCreationResponse:
        group = result.group
        return AccessGroupCreationResponse(
            **AccessGroupMapper._fields(
                result.operation, group.project_id, group.group_id, group.access_revision
            ),
            name=group.name.value,
            display_name=group.display_name,
            creator_principal_id=group.creator_principal_id.value,
        )

    @staticmethod
    def metadata(group: AccessGroupMetadataDTO) -> AccessGroupMetadataResponse:
        return AccessGroupMetadataResponse(
            project_id=group.project_id.value,
            access_group_id=group.group_id.value,
            name=group.name.value if group.name is not None else None,
            display_name=group.display_name,
            created_at=group.created_at,
            access_revision=group.access_revision,
        )

    @staticmethod
    def page(page: AccessGroupPrincipalsPageDTO) -> AccessGroupPrincipalsPageResponse:
        return AccessGroupPrincipalsPageResponse(
            project_id=page.project_id.value,
            access_group_id=page.group_id.value,
            access_revision=page.access_revision,
            items=[
                AccessGroupPrincipalResponse(
                    principal_id=item.principal_id.value,
                    kind=item.kind,
                    display_name=item.display_name,
                )
                for item in page.items
            ],
            next_cursor=page.next_cursor,
        )

    @staticmethod
    def membership(result: AccessGroupRelationshipResultDTO) -> AccessGroupMembershipResponse:
        return AccessGroupMembershipResponse(
            **AccessGroupMapper._fields(
                result.operation, result.project_id, result.group_id, result.access_revision
            ),
            principal_id=result.principal_id.value,
            member=True,
            changed=result.changed,
        )

    @staticmethod
    def membership_removal(
        result: AccessGroupRelationshipResultDTO,
    ) -> AccessGroupMembershipRemovalResponse:
        return AccessGroupMembershipRemovalResponse(
            **AccessGroupMapper._fields(
                result.operation, result.project_id, result.group_id, result.access_revision
            ),
            principal_id=result.principal_id.value,
            removed=True,
            changed=result.changed,
        )

    @staticmethod
    def manager(result: AccessGroupRelationshipResultDTO) -> AccessGroupManagerResponse:
        return AccessGroupManagerResponse(
            **AccessGroupMapper._fields(
                result.operation, result.project_id, result.group_id, result.access_revision
            ),
            principal_id=result.principal_id.value,
            manager=True,
            changed=result.changed,
        )

    @staticmethod
    def manager_removal(
        result: AccessGroupRelationshipResultDTO,
    ) -> AccessGroupManagerRemovalResponse:
        return AccessGroupManagerRemovalResponse(
            **AccessGroupMapper._fields(
                result.operation, result.project_id, result.group_id, result.access_revision
            ),
            principal_id=result.principal_id.value,
            removed=True,
            changed=result.changed,
        )

    @staticmethod
    def deletion(result: AccessGroupDeletionResultDTO) -> AccessGroupDeletionResponse:
        group = result.group
        return AccessGroupDeletionResponse(
            **AccessGroupMapper._fields(
                result.operation, group.project_id, group.group_id, group.access_revision
            ),
            removed=True,
        )
