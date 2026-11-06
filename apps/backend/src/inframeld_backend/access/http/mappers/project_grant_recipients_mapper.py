from uuid import UUID

from inframeld_backend.access.application.dtos.access_group_grant_target_dto import (
    AccessGroupGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.application_account_grant_target_dto import (
    ApplicationAccountGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.grant_recipients_page_dto import (
    GrantRecipientsPageDTO,
)
from inframeld_backend.access.application.dtos.project_grant_target_dto import ProjectGrantTargetDTO
from inframeld_backend.access.application.queries.list_project_grant_recipients_query import (
    ListProjectGrantRecipientsQuery,
)
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.enums.grant_target_kind import GrantTargetKind
from inframeld_backend.access.http.responses.grant_recipient_response import GrantRecipientResponse
from inframeld_backend.shared.application.errors.application_errors import InvalidInputError
from inframeld_backend.shared.http.requests.pagination_query import PaginationQuery
from inframeld_backend.shared.http.responses.page_response import PageResponse


class ProjectGrantRecipientsMapper:
    """Convert the closed scalar target into a query without granting target visibility."""

    @staticmethod
    def query(
        *,
        project_id: UUID,
        target_kind: GrantTargetKind,
        target_id: UUID,
        action_id: str,
        pagination: PaginationQuery,
    ) -> ListProjectGrantRecipientsQuery:
        project = ProjectId(project_id)
        target: ProjectGrantTargetDTO | AccessGroupGrantTargetDTO | ApplicationAccountGrantTargetDTO
        if target_kind is GrantTargetKind.PROJECT:
            target = ProjectGrantTargetDTO(project_id=ProjectId(target_id))
        elif target_kind is GrantTargetKind.ACCESS_GROUP:
            target = AccessGroupGrantTargetDTO(
                project_id=project, access_group_id=AccessGroupId(target_id)
            )
        else:
            target = ApplicationAccountGrantTargetDTO(
                project_id=project, application_principal_id=PrincipalId(target_id)
            )
        try:
            return ListProjectGrantRecipientsQuery(
                project_id=project,
                target=target,
                action_id=ActionId(action_id),
                limit=pagination.limit,
                cursor=pagination.cursor,
            )
        except ValueError as error:
            raise InvalidInputError("The exact recipient query is invalid.") from error

    @staticmethod
    def response(page: GrantRecipientsPageDTO) -> PageResponse[GrantRecipientResponse]:
        return PageResponse[GrantRecipientResponse](
            items=[
                GrantRecipientResponse(
                    principal_id=item.principal_id.value,
                    display_name=item.display_name,
                    kind=item.kind,
                )
                for item in page.items
            ],
            next_cursor=page.next_cursor,
        )
