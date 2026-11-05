from uuid import UUID

from inframeld_backend.access.application.dtos.project_action_grants_page_dto import (
    ProjectActionGrantsPageDTO,
)
from inframeld_backend.access.application.queries.list_project_action_grants_query import (
    ListProjectActionGrantsQuery,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.responses.project_action_grant_item_response import (
    ProjectActionGrantItemResponse,
)
from inframeld_backend.shared.application.errors.application_errors import InvalidInputError
from inframeld_backend.shared.http.requests.pagination_query import PaginationQuery
from inframeld_backend.shared.http.responses.page_response import PageResponse


class ProjectActionGrantMapper:
    @staticmethod
    def query(
        *, project_id: UUID, action_id: str, pagination: PaginationQuery
    ) -> ListProjectActionGrantsQuery:
        try:
            return ListProjectActionGrantsQuery(
                ProjectId(project_id), ActionId(action_id), pagination.limit, pagination.cursor
            )
        except ValueError as error:
            raise InvalidInputError("The Project grant query is invalid.") from error

    @staticmethod
    def response(page: ProjectActionGrantsPageDTO) -> PageResponse[ProjectActionGrantItemResponse]:
        return PageResponse[ProjectActionGrantItemResponse](
            items=[
                ProjectActionGrantItemResponse(
                    project_id=page.project_id.value,
                    recipient_principal_id=item.recipient_principal_id.value,
                    action_id=item.action_id.value,
                    can_grant=item.can_grant,
                )
                for item in page.items
            ],
            next_cursor=page.next_cursor,
        )
