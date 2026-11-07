import asyncio
from typing import override

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.organization_action_grants_page_dto import (
    OrganizationActionGrantsPageDTO,
)
from inframeld_backend.access.application.dtos.organization_grant_target_dto import (
    OrganizationGrantTargetDTO,
)
from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
)
from inframeld_backend.access.application.protocols.organization_action_grants_facts_reader import (
    OrganizationActionGrantsFactsReader,
)
from inframeld_backend.access.application.protocols.organization_action_grants_reader import (
    OrganizationActionGrantsReader,
)
from inframeld_backend.access.application.queries.list_organization_action_grants_query import (
    ListOrganizationActionGrantsQuery,
)
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.application.value_objects.access_action_grants_cursor import (
    AccessActionGrantsCursor,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.policies.organization_grant_policy import (
    OrganizationGrantPolicy,
)
from inframeld_backend.access.domain.policies.principal_access_policy import PrincipalAccessPolicy
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    DependencyUnavailableError,
    InvalidInputError,
    ResourceNotFoundError,
)


class OrganizationActionGrantsService(OrganizationActionGrantsReader):
    def __init__(
        self, organization_grants_facts_reader: OrganizationActionGrantsFactsReader
    ) -> None:
        self._organization_grants_facts_reader = organization_grants_facts_reader

    @override
    async def list_grants(
        self, *, access: AccessContextDTO, query: ListOrganizationActionGrantsQuery
    ) -> OrganizationActionGrantsPageDTO:
        if not OrganizationGrantPolicy.supports_action(query.action_id):
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
                facts = await self._organization_grants_facts_reader.read_page(
                    access=access,
                    organization_id=query.organization_id,
                    action_id=query.action_id,
                    after=cursor.after if cursor is not None else None,
                    limit=query.limit,
                )
        except TimeoutError as error:
            raise DependencyUnavailableError() from error
        if facts is None:
            raise ResourceNotFoundError()
        if (
            facts.organization_id != query.organization_id
            or facts.action_id != query.action_id
            or facts.actor.id != access.actor_principal_id
            or facts.actor.organization_id != facts.organization_id
        ):
            raise RuntimeError("The grant page changed its current actor or scope.")
        PrincipalAccessEvaluationService.require_human(access=access, principal=facts.actor)
        eligibility = PrincipalAccessEvaluationService.evaluate(
            access=access,
            principal=facts.actor,
            has_pending_recovery=facts.actor_has_pending_recovery,
            oauth_credential_facts=facts.actor_oauth_credential_facts,
        )
        if not eligibility.credential_is_current:
            raise HumanOAuthCredentialRejectedError()
        if facts.actor.kind is not PrincipalKind.HUMAN or not PrincipalAccessPolicy.may_use_product(
            eligibility
        ):
            raise AccessDeniedError()
        if not OrganizationGrantPolicy.may_manage(
            actor_access=eligibility, can_grant_action=facts.actor_can_grant
        ):
            raise AccessDeniedError()
        target = OrganizationGrantTargetDTO(organization_id=facts.organization_id)
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
        return OrganizationActionGrantsPageDTO(
            organization_id=facts.organization_id,
            action_id=query.action_id,
            items=items,
            next_cursor=continuation,
        )
