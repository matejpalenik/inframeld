import asyncio
from typing import override

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_action_grants_page_dto import (
    ProjectActionGrantsPageDTO,
)
from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
)
from inframeld_backend.access.application.protocols.project_action_grants_facts_reader import (
    ProjectActionGrantsFactsReader,
)
from inframeld_backend.access.application.protocols.project_action_grants_reader import (
    ProjectActionGrantsReader,
)
from inframeld_backend.access.application.queries.list_project_action_grants_query import (
    ListProjectActionGrantsQuery,
)
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.application.value_objects.project_action_grants_cursor import (
    ProjectActionGrantsCursor,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.policies.principal_access_policy import PrincipalAccessPolicy
from inframeld_backend.access.domain.policies.project_action_eligibility_policy import (
    ProjectActionEligibilityPolicy,
)
from inframeld_backend.access.domain.policies.project_grant_delegation_policy import (
    ProjectGrantDelegationPolicy,
)
from inframeld_backend.access.domain.policies.project_visibility_policy import (
    ProjectVisibilityPolicy,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    DependencyUnavailableError,
    InvalidInputError,
    ResourceNotFoundError,
)


class ProjectActionGrantsService(ProjectActionGrantsReader):
    def __init__(self, grants_facts_reader: ProjectActionGrantsFactsReader) -> None:
        self._grants_facts_reader = grants_facts_reader

    @override
    async def list_grants(
        self,
        *,
        access: AccessContextDTO,
        query: ListProjectActionGrantsQuery,
    ) -> ProjectActionGrantsPageDTO:
        if not ProjectActionEligibilityPolicy.may_use(
            action_id=query.action_id, principal_kind=PrincipalKind.HUMAN
        ):
            raise InvalidInputError("The action is not supported for this target.")

        try:
            cursor = (
                ProjectActionGrantsCursor.from_token(query.cursor)
                if query.cursor is not None
                else None
            )
        except ValueError as error:
            raise InvalidInputError(
                "The continuation cursor is invalid or incompatible."
            ) from error

        try:
            async with asyncio.timeout(5):
                facts = await self._grants_facts_reader.read_page(
                    access=access,
                    project_id=query.project_id,
                    action_id=query.action_id,
                    after=cursor.after if cursor is not None else None,
                    limit=query.limit,
                )
        except TimeoutError as error:
            raise DependencyUnavailableError() from error

        if facts is None:
            raise ResourceNotFoundError()

        action = facts.action
        if (
            facts.project_id != query.project_id
            or facts.action_id != query.action_id
            or action.principal.id != access.actor_principal_id
            or facts.organization_id != action.principal.organization_id
        ):
            raise RuntimeError("The Project action grants observation changed its actor or scope.")

        PrincipalAccessEvaluationService.require_human(access=access, principal=action.principal)
        eligibility = PrincipalAccessEvaluationService.evaluate(
            access=access,
            principal=action.principal,
            has_pending_recovery=action.has_pending_recovery,
            oauth_credential_facts=action.oauth_credential_facts,
        )
        if not eligibility.credential_is_current:
            raise HumanOAuthCredentialRejectedError()

        if (
            action.principal.kind is not PrincipalKind.HUMAN
            or not PrincipalAccessPolicy.may_use_product(eligibility)
        ):
            raise AccessDeniedError()

        if not ProjectVisibilityPolicy.may_view_project(
            principal_status=action.principal.status,
            project_status=action.project_status,
            is_project_member=action.is_project_member,
        ):
            raise ResourceNotFoundError()

        if (
            not action.has_exact_action_grant
            or not ProjectGrantDelegationPolicy.may_delegate_project_action(
                actor_access=eligibility,
                actor_is_project_member=action.is_project_member,
                actor_can_grant_action=facts.actor_can_grant_action,
            )
        ):
            raise AccessDeniedError()

        if cursor is not None and (
            cursor.installation_id,
            cursor.organization_id,
            cursor.project_id,
            cursor.action_id,
        ) != (facts.installation_id, facts.organization_id, facts.project_id, facts.action_id):
            raise InvalidInputError("The continuation cursor is invalid or incompatible.")

        if len(facts.items) > query.limit + 1:
            raise RuntimeError("The Project action grants observation exceeded its bound.")

        previous = cursor.after.value.int if cursor is not None else -1
        for item in facts.items:
            current = item.recipient_principal_id.value.int
            if current <= previous or item.action_id != query.action_id:
                raise RuntimeError(
                    "The Project action grants observation violated action, position or order."
                )
            previous = current

        items = facts.items[: query.limit]
        continuation = (
            ProjectActionGrantsCursor(
                facts.installation_id,
                facts.organization_id,
                facts.project_id,
                facts.action_id,
                items[-1].recipient_principal_id,
            ).to_token()
            if len(facts.items) > query.limit
            else None
        )
        return ProjectActionGrantsPageDTO(facts.project_id, facts.action_id, items, continuation)
