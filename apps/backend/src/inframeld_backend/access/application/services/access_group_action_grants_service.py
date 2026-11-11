import asyncio
from typing import override

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.access_group_action_grants_page_dto import (
    AccessGroupActionGrantsPageDTO,
)
from inframeld_backend.access.application.dtos.access_group_grant_target_dto import (
    AccessGroupGrantTargetDTO,
)
from inframeld_backend.access.application.protocols.access_group_action_grants_facts_reader import (
    AccessGroupActionGrantsFactsReader,
)
from inframeld_backend.access.application.protocols.access_group_action_grants_reader import (
    AccessGroupActionGrantsReader,
)
from inframeld_backend.access.application.queries.list_access_group_action_grants_query import (
    ListAccessGroupActionGrantsQuery,
)
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.application.value_objects.access_action_grants_cursor import (
    AccessActionGrantsCursor,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.policies.access_group_grant_policy import (
    AccessGroupGrantPolicy,
)
from inframeld_backend.access.domain.policies.principal_access_policy import PrincipalAccessPolicy
from inframeld_backend.access.domain.policies.project_visibility_policy import (
    ProjectVisibilityPolicy,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    DependencyUnavailableError,
    InvalidInputError,
    ResourceNotFoundError,
)


class AccessGroupActionGrantsService(AccessGroupActionGrantsReader):
    def __init__(
        self, access_group_grants_facts_reader: AccessGroupActionGrantsFactsReader
    ) -> None:
        self._access_group_grants_facts_reader = access_group_grants_facts_reader

    @override
    async def list_grants(
        self, *, access: AccessContextDTO, query: ListAccessGroupActionGrantsQuery
    ) -> AccessGroupActionGrantsPageDTO:
        if not AccessGroupGrantPolicy.supports_recipient(
            action_id=query.action_id, kind=PrincipalKind.HUMAN, can_grant=True
        ):
            raise InvalidInputError("The action is not supported for this target.")
        try:
            cursor = (
                AccessActionGrantsCursor.from_token(query.cursor)
                if query.cursor is not None
                else None
            )
        except ValueError as error:
            raise InvalidInputError(
                "The continuation cursor is invalid or incompatible."
            ) from error
        try:
            async with asyncio.timeout(5):
                facts = await self._access_group_grants_facts_reader.read_page(
                    access=access,
                    project_id=query.project_id,
                    group_id=query.group_id,
                    action_id=query.action_id,
                    after=cursor.after if cursor is not None else None,
                    limit=query.limit,
                )
        except TimeoutError as error:
            raise DependencyUnavailableError() from error
        if facts is None:
            raise ResourceNotFoundError()
        if (
            facts.group_id != query.group_id
            or facts.project_id != query.project_id
            or facts.action_id != query.action_id
            or facts.actor.principal.id != access.actor_principal_id
            or facts.actor.principal.organization_id != facts.organization_id
        ):
            raise RuntimeError("The grant page changed its current actor or scope.")
        PrincipalAccessEvaluationService.require_human(
            access=access, principal=facts.actor.principal
        )
        eligibility = PrincipalAccessEvaluationService.evaluate(
            access=access,
            principal=facts.actor.principal,
            has_pending_recovery=facts.actor.has_pending_recovery,
            oauth_credential_facts=facts.actor.oauth_credential_facts,
        )
        PrincipalAccessEvaluationService.require_current_credential(
            access=access, principal_access=eligibility
        )
        if not ProjectVisibilityPolicy.may_view_project(
            principal_status=facts.actor.principal.status,
            project_status=facts.actor.project_status,
            is_project_member=facts.actor.is_project_member,
        ):
            raise ResourceNotFoundError()
        if (
            facts.actor.principal.kind is not PrincipalKind.HUMAN
            or not PrincipalAccessPolicy.may_use_product(eligibility)
        ):
            raise AccessDeniedError()
        if not AccessGroupGrantPolicy.may_manage(
            actor_access=eligibility,
            is_project_member=facts.actor.is_project_member,
            can_grant_action=facts.actor_can_grant,
            is_group_member=facts.actor_is_group_member,
            is_group_manager=facts.actor_is_group_manager,
        ):
            raise AccessDeniedError()
        target = AccessGroupGrantTargetDTO(
            project_id=facts.project_id, access_group_id=facts.group_id
        )
        if cursor is not None and (
            cursor.installation_id,
            cursor.organization_id,
            cursor.target,
            cursor.action_id,
        ) != (
            facts.installation_id,
            facts.organization_id,
            target,
            facts.action_id,
        ):
            raise InvalidInputError("The continuation cursor is invalid or incompatible.")
        if len(facts.items) > query.limit + 1:
            raise RuntimeError("The assignment page exceeded its bound.")
        previous = cursor.after.value.int if cursor is not None else -1
        for item in facts.items:
            current = item.recipient_principal_id.value.int
            if current <= previous or item.action_id != query.action_id:
                raise RuntimeError("The assignment page violated action, position or order.")
            previous = current
        items = facts.items[: query.limit]
        continuation = (
            AccessActionGrantsCursor(
                installation_id=facts.installation_id,
                organization_id=facts.organization_id,
                target=target,
                action_id=query.action_id,
                after=items[-1].recipient_principal_id,
            ).to_token()
            if len(facts.items) > query.limit
            else None
        )
        return AccessGroupActionGrantsPageDTO(
            project_id=facts.project_id,
            group_id=facts.group_id,
            action_id=query.action_id,
            items=items,
            next_cursor=continuation,
        )
