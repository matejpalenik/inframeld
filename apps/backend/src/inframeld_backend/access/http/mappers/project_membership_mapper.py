from typing import Literal
from uuid import UUID

from inframeld_backend.access.application.commands.add_project_member_command import (
    AddProjectMemberCommand,
)
from inframeld_backend.access.application.commands.remove_project_member_command import (
    RemoveProjectMemberCommand,
)
from inframeld_backend.access.application.dtos.project_membership_change_result_dto import (
    ProjectMembershipChangeResultDTO,
)
from inframeld_backend.access.application.enums.project_membership_change_kind import (
    ProjectMembershipChangeKind,
)
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.requests.project_membership_request import (
    ProjectMembershipRequest,
)
from inframeld_backend.access.http.responses.project_membership_removal_response import (
    ProjectMembershipRemovalResponse,
)
from inframeld_backend.access.http.responses.project_membership_response import (
    ProjectMembershipResponse,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import (
    IdempotencyContextDTO,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey


class ProjectMembershipMapper:
    @staticmethod
    def add_command(
        project_id: UUID, principal_id: UUID, body: ProjectMembershipRequest
    ) -> AddProjectMemberCommand:
        return AddProjectMemberCommand(
            ProjectId(project_id), PrincipalId(principal_id), body.expected_access_revision
        )

    @staticmethod
    def remove_command(
        project_id: UUID, principal_id: UUID, revision: int
    ) -> RemoveProjectMemberCommand:
        return RemoveProjectMemberCommand(
            ProjectId(project_id), PrincipalId(principal_id), revision
        )

    @staticmethod
    def context(
        project_id: UUID,
        principal_id: UUID,
        method: Literal[HttpMethod.PUT, HttpMethod.DELETE],
        key: IdempotencyKey,
    ) -> IdempotencyContextDTO:
        return IdempotencyContextDTO(
            method, f"/v1/projects/{project_id}/members/{principal_id}", key
        )

    @staticmethod
    def add_response(result: ProjectMembershipChangeResultDTO) -> ProjectMembershipResponse:
        if result.change_kind is not ProjectMembershipChangeKind.ADD:
            raise RuntimeError("Membership addition returned another operation's result.")
        return ProjectMembershipResponse(
            operation_id=result.operation.operation_id.value,
            idempotency_expires_at=result.operation.expires_at,
            project_id=result.project_id.value,
            principal_id=result.principal_id.value,
            access_revision=result.access_revision,
            member=True,
            changed=result.changed,
        )

    @staticmethod
    def remove_response(
        result: ProjectMembershipChangeResultDTO,
    ) -> ProjectMembershipRemovalResponse:
        if result.change_kind is not ProjectMembershipChangeKind.REMOVE:
            raise RuntimeError("Membership removal returned another operation's result.")
        return ProjectMembershipRemovalResponse(
            operation_id=result.operation.operation_id.value,
            idempotency_expires_at=result.operation.expires_at,
            project_id=result.project_id.value,
            principal_id=result.principal_id.value,
            access_revision=result.access_revision,
            removed=True,
            changed=result.changed,
        )
