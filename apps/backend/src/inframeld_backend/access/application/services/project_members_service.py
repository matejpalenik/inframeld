import asyncio
from typing import override

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_members_page_dto import ProjectMembersPageDTO
from inframeld_backend.access.application.dtos.project_membership_observation_dto import (
    ProjectMembershipObservationDTO,
)
from inframeld_backend.access.application.protocols.project_members_facts_reader import (
    ProjectMembersFactsReader,
)
from inframeld_backend.access.application.protocols.project_members_reader import (
    ProjectMembersReader,
)
from inframeld_backend.access.application.queries.list_project_members_query import (
    ListProjectMembersQuery,
)
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.application.value_objects.project_members_cursor import (
    ProjectMembersCursor,
)
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.policies.principal_access_policy import PrincipalAccessPolicy
from inframeld_backend.access.domain.policies.project_action_eligibility_policy import (
    ProjectActionEligibilityPolicy,
)
from inframeld_backend.access.domain.policies.project_visibility_policy import (
    ProjectVisibilityPolicy,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    DependencyUnavailableError,
    InvalidInputError,
    ResourceNotFoundError,
)


class ProjectMembersService(ProjectMembersReader):
    def __init__(self, project_members_facts_reader: ProjectMembersFactsReader) -> None:
        self._project_members_facts_reader = project_members_facts_reader

    @override
    async def list_members(
        self, *, access: AccessContextDTO, query: ListProjectMembersQuery
    ) -> ProjectMembersPageDTO:
        try:
            cursor = (
                ProjectMembersCursor.from_token(query.cursor) if query.cursor is not None else None
            )
        except ValueError as error:
            raise InvalidInputError(
                "The continuation cursor is invalid or incompatible."
            ) from error
        try:
            async with asyncio.timeout(5):
                facts = await self._project_members_facts_reader.read_page(
                    access=access,
                    project_id=query.project_id,
                    after=cursor.after if cursor is not None else None,
                    limit=query.limit,
                )
        except TimeoutError as error:
            raise DependencyUnavailableError() from error
        facts = ProjectMembershipObservationDTO.require_requested_scope(
            observation=facts,
            actor_principal_id=access.actor_principal_id,
            project_id=query.project_id,
        )
        action = facts.action
        PrincipalAccessEvaluationService.require_human(access=access, principal=action.principal)
        eligibility = PrincipalAccessEvaluationService.evaluate(
            access=access,
            principal=action.principal,
            has_pending_recovery=action.has_pending_recovery,
            oauth_credential_facts=action.oauth_credential_facts,
        )
        PrincipalAccessEvaluationService.require_current_credential(
            access=access, principal_access=eligibility
        )
        if not PrincipalAccessPolicy.may_use_product(
            eligibility
        ) or not ProjectActionEligibilityPolicy.may_use(
            action_id=ActionId(ProjectAction.MANAGE_PROJECT_MEMBERS.value),
            principal_kind=action.principal.kind,
        ):
            raise AccessDeniedError()
        if not ProjectVisibilityPolicy.may_view_project(
            principal_status=action.principal.status,
            project_status=action.project_status,
            is_project_member=action.is_project_member,
        ):
            raise ResourceNotFoundError()
        if not action.has_exact_action_grant:
            raise AccessDeniedError()
        if cursor is not None and (
            cursor.installation_id,
            cursor.organization_id,
            cursor.project_id,
        ) != (facts.installation_id, facts.organization_id, facts.project_id):
            raise InvalidInputError("The continuation cursor is invalid or incompatible.")
        if len(facts.members) > query.limit + 1:
            raise RuntimeError("The Project members observation exceeded its bound.")
        previous = cursor.after.value.int if cursor is not None else -1
        for member in facts.members:
            current = member.principal_id.value.int
            if current <= previous:
                raise RuntimeError("The Project members observation violated position or order.")
            previous = current
        items = facts.members[: query.limit]
        continuation = (
            ProjectMembersCursor(
                facts.installation_id,
                facts.organization_id,
                facts.project_id,
                items[-1].principal_id,
            ).to_token()
            if len(facts.members) > query.limit
            else None
        )
        return ProjectMembersPageDTO(facts.project_id, facts.access_revision, items, continuation)
