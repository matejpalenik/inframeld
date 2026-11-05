from uuid import UUID

from inframeld_backend.access.application.dtos.access_group_grant_target_dto import (
    AccessGroupGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.application_account_grant_target_dto import (
    ApplicationAccountGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.my_project_access_page_dto import (
    MyProjectAccessPageDTO,
)
from inframeld_backend.access.application.dtos.project_grant_target_dto import ProjectGrantTargetDTO
from inframeld_backend.access.application.queries.get_my_project_access_query import (
    GetMyProjectAccessQuery,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.enums.grant_target_kind import GrantTargetKind
from inframeld_backend.access.http.responses.access_group_grant_target_response import (
    AccessGroupGrantTargetResponse,
)
from inframeld_backend.access.http.responses.application_account_grant_target_response import (
    ApplicationAccountGrantTargetResponse,
)
from inframeld_backend.access.http.responses.my_project_access_grant_response import (
    MyProjectAccessGrantResponse,
)
from inframeld_backend.access.http.responses.my_project_access_group_response import (
    MyProjectAccessGroupResponse,
)
from inframeld_backend.access.http.responses.my_project_access_response import (
    MyProjectAccessResponse,
)
from inframeld_backend.access.http.responses.project_grant_target_response import (
    ProjectGrantTargetResponse,
)
from inframeld_backend.shared.application.errors.application_errors import InvalidInputError
from inframeld_backend.shared.http.requests.pagination_query import PaginationQuery


class MyProjectAccessMapper:
    @staticmethod
    def query(*, project_id: UUID, pagination: PaginationQuery) -> GetMyProjectAccessQuery:
        try:
            return GetMyProjectAccessQuery(
                ProjectId(project_id), pagination.limit, pagination.cursor
            )
        except ValueError as error:
            raise InvalidInputError("The own-access query is invalid.") from error

    @staticmethod
    def _target(
        target: ProjectGrantTargetDTO
        | AccessGroupGrantTargetDTO
        | ApplicationAccountGrantTargetDTO,
    ) -> (
        ProjectGrantTargetResponse
        | AccessGroupGrantTargetResponse
        | ApplicationAccountGrantTargetResponse
    ):
        if isinstance(target, ProjectGrantTargetDTO):
            return ProjectGrantTargetResponse(
                kind=GrantTargetKind.PROJECT, project_id=target.project_id.value
            )
        if isinstance(target, AccessGroupGrantTargetDTO):
            return AccessGroupGrantTargetResponse(
                kind=GrantTargetKind.ACCESS_GROUP,
                project_id=target.project_id.value,
                access_group_id=target.access_group_id.value,
            )
        return ApplicationAccountGrantTargetResponse(
            kind=GrantTargetKind.APPLICATION_ACCOUNT,
            project_id=target.project_id.value,
            application_principal_id=target.application_principal_id.value,
        )

    @staticmethod
    def response(page: MyProjectAccessPageDTO) -> MyProjectAccessResponse:
        return MyProjectAccessResponse(
            project_id=page.project_id.value,
            principal_id=page.principal_id.value,
            access_revision=page.access_revision,
            grants=[
                MyProjectAccessGrantResponse(
                    target=MyProjectAccessMapper._target(item.target),
                    action_id=item.action_id.value,
                    can_grant=item.can_grant,
                )
                for item in page.grants
            ],
            group_memberships=[
                MyProjectAccessGroupResponse(access_group_id=x.value)
                for x in page.group_memberships
            ],
            group_managements=[
                MyProjectAccessGroupResponse(access_group_id=x.value)
                for x in page.group_managements
            ],
            next_cursor=page.next_cursor,
        )
