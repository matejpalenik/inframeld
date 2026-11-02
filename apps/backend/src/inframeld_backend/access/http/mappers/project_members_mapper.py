from uuid import UUID

from inframeld_backend.access.application.dtos.project_members_page_dto import ProjectMembersPageDTO
from inframeld_backend.access.application.queries.list_project_members_query import (
    ListProjectMembersQuery,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.responses.project_member_response import ProjectMemberResponse
from inframeld_backend.access.http.responses.project_members_page_response import (
    ProjectMembersPageResponse,
)
from inframeld_backend.shared.http.requests.pagination_query import PaginationQuery


class ProjectMembersMapper:
    @staticmethod
    def query(*, project_id: UUID, pagination: PaginationQuery) -> ListProjectMembersQuery:
        return ListProjectMembersQuery(ProjectId(project_id), pagination.limit, pagination.cursor)

    @staticmethod
    def response(page: ProjectMembersPageDTO) -> ProjectMembersPageResponse:
        return ProjectMembersPageResponse(
            project_id=page.project_id.value,
            access_revision=page.access_revision,
            items=[
                ProjectMemberResponse(
                    principal_id=member.principal_id.value,
                    display_name=member.display_name,
                    kind=member.kind,
                )
                for member in page.items
            ],
            next_cursor=page.next_cursor,
        )
