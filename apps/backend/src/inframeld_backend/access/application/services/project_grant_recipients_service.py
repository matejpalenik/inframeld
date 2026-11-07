import asyncio
from typing import override

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.access_group_grant_target_dto import (
    AccessGroupGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.application_account_grant_target_dto import (
    ApplicationAccountGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.grant_recipient_candidate_dto import (
    GrantRecipientCandidateDTO,
)
from inframeld_backend.access.application.dtos.grant_recipient_dto import GrantRecipientDTO
from inframeld_backend.access.application.dtos.grant_recipients_page_dto import (
    GrantRecipientsPageDTO,
)
from inframeld_backend.access.application.dtos.project_grant_target_dto import ProjectGrantTargetDTO
from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
)
from inframeld_backend.access.application.protocols.grant_recipients_facts_reader import (
    GrantRecipientsFactsReader,
)
from inframeld_backend.access.application.protocols.project_grant_recipients_reader import (
    ProjectGrantRecipientsReader,
)
from inframeld_backend.access.application.queries.list_project_grant_recipients_query import (
    ListProjectGrantRecipientsQuery,
)
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.application.value_objects.grant_recipients_cursor import (
    GrantRecipientsCursor,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.policies.access_group_grant_policy import (
    AccessGroupGrantPolicy,
)
from inframeld_backend.access.domain.policies.application_account_grant_policy import (
    ApplicationAccountGrantPolicy,
)
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
from inframeld_backend.access.domain.policy_inputs.principal_access_policy_input import (
    PrincipalAccessPolicyInput,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    DependencyUnavailableError,
    InvalidInputError,
    ResourceNotFoundError,
)


class ProjectGrantRecipientsService(ProjectGrantRecipientsReader):
    """Disclose only an authorized, bounded page of currently eligible choices."""

    def __init__(self, grant_recipients_facts_reader: GrantRecipientsFactsReader) -> None:
        self._grant_recipients_facts_reader = grant_recipients_facts_reader

    @override
    async def list_recipients(
        self, *, access: AccessContextDTO, query: ListProjectGrantRecipientsQuery
    ) -> GrantRecipientsPageDTO:
        eligible_kinds = tuple(
            kind
            for kind in PrincipalKind
            if self._supports_kind(
                target=query.target,
                action_id=query.action_id,
                kind=kind,
            )
        )
        if PrincipalKind.HUMAN not in eligible_kinds:
            raise InvalidInputError("The action is not supported for this target.")
        try:
            cursor = (
                GrantRecipientsCursor.from_token(query.cursor) if query.cursor is not None else None
            )
        except ValueError as error:
            raise InvalidInputError(
                "The continuation cursor is invalid or incompatible."
            ) from error
        try:
            async with asyncio.timeout(5):
                facts = await self._grant_recipients_facts_reader.read_page(
                    access=access,
                    project_id=query.project_id,
                    target=query.target,
                    action_id=query.action_id,
                    eligible_kinds=eligible_kinds,
                    after=cursor.after if cursor is not None else None,
                    limit=query.limit,
                )
        except TimeoutError as error:
            raise DependencyUnavailableError() from error
        if facts is None:
            raise ResourceNotFoundError()
        if (
            facts.project_id != query.project_id
            or facts.target != query.target
            or facts.action_id != query.action_id
            or facts.actor.principal.id != access.actor_principal_id
            or facts.actor.principal.organization_id != facts.organization_id
        ):
            raise RuntimeError("The eligible-recipient observation changed actor or exact scope.")
        PrincipalAccessEvaluationService.require_human(
            access=access, principal=facts.actor.principal
        )
        eligibility = PrincipalAccessEvaluationService.evaluate(
            access=access,
            principal=facts.actor.principal,
            has_pending_recovery=facts.actor.has_pending_recovery,
            oauth_credential_facts=facts.actor.oauth_credential_facts,
        )
        if not eligibility.credential_is_current:
            raise HumanOAuthCredentialRejectedError()
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
        if isinstance(query.target, AccessGroupGrantTargetDTO):
            relationships = facts.actor_group_relationships
            if relationships is None:
                raise RuntimeError("The group target has no current relationship observations.")
            permitted = AccessGroupGrantPolicy.may_manage(
                actor_access=eligibility,
                is_project_member=facts.actor.is_project_member,
                can_grant_action=facts.actor_can_grant,
                is_group_member=relationships.member,
                is_group_manager=relationships.manager,
            )
        else:
            if facts.actor_group_relationships is not None:
                raise RuntimeError("The target acquired an unrelated group-management alternative.")
            permitted = ProjectGrantDelegationPolicy.may_delegate_project_action(
                actor_access=eligibility,
                actor_is_project_member=facts.actor.is_project_member,
                actor_can_grant_action=facts.actor_can_grant,
            )
        if not permitted:
            raise AccessDeniedError()
        if cursor is not None and (
            cursor.installation_id,
            cursor.organization_id,
            cursor.target,
            cursor.action_id,
        ) != (
            facts.installation_id,
            facts.organization_id,
            facts.target,
            facts.action_id,
        ):
            raise InvalidInputError("The continuation cursor is invalid or incompatible.")
        if len(facts.items) > query.limit + 1:
            raise RuntimeError("The eligible-recipient observation exceeded its bound.")
        previous = cursor.after.value.int if cursor is not None else -1
        for candidate in facts.items:
            current = candidate.principal.id.value.int
            if (
                current <= previous
                or candidate.principal.organization_id != facts.organization_id
                or candidate.principal.kind not in eligible_kinds
            ):
                raise RuntimeError(
                    "The recipient page violated scope, catalogue, position or order."
                )
            if not self._eligible(
                target=query.target, action_id=query.action_id, candidate=candidate
            ):
                raise RuntimeError(
                    "The recipient page was not filtered for eligibility before its limit."
                )
            previous = current
        selected = facts.items[: query.limit]
        continuation = (
            GrantRecipientsCursor(
                installation_id=facts.installation_id,
                organization_id=facts.organization_id,
                target=facts.target,
                action_id=facts.action_id,
                after=selected[-1].principal.id,
            ).to_token()
            if len(facts.items) > query.limit
            else None
        )
        return GrantRecipientsPageDTO(
            items=tuple(
                GrantRecipientDTO(
                    principal_id=item.principal.id,
                    display_name=item.display_name,
                    kind=item.principal.kind,
                )
                for item in selected
            ),
            next_cursor=continuation,
        )

    @staticmethod
    def _supports_kind(
        *,
        target: ProjectGrantTargetDTO
        | AccessGroupGrantTargetDTO
        | ApplicationAccountGrantTargetDTO,
        action_id: ActionId,
        kind: PrincipalKind,
    ) -> bool:
        if isinstance(target, ProjectGrantTargetDTO):
            return ProjectActionEligibilityPolicy.may_use(action_id=action_id, principal_kind=kind)
        if isinstance(target, AccessGroupGrantTargetDTO):
            return AccessGroupGrantPolicy.supports_recipient(
                action_id=action_id, kind=kind, can_grant=False
            )
        return ApplicationAccountGrantPolicy.supports_recipient(action_id=action_id, kind=kind)

    @staticmethod
    def _eligible(
        *,
        target: ProjectGrantTargetDTO
        | AccessGroupGrantTargetDTO
        | ApplicationAccountGrantTargetDTO,
        action_id: ActionId,
        candidate: GrantRecipientCandidateDTO,
    ) -> bool:
        access = PrincipalAccessPolicyInput(
            principal=candidate.principal,
            has_pending_recovery=candidate.has_pending_recovery,
            credential_is_current=True,
        )
        if isinstance(target, ProjectGrantTargetDTO):
            return ProjectGrantDelegationPolicy.may_assign_to_recipient(
                recipient_access=access,
                is_project_member=candidate.is_project_member,
                has_coherent_identity=candidate.has_coherent_identity,
                application_is_project_bound=candidate.application_is_project_bound,
                action_id=action_id,
                can_grant=False,
            )
        if isinstance(target, AccessGroupGrantTargetDTO):
            return AccessGroupGrantPolicy.may_receive(
                recipient_access=access,
                is_project_member=candidate.is_project_member,
                has_coherent_identity=candidate.has_coherent_identity,
                application_is_bound=candidate.application_is_project_bound,
            )
        return ApplicationAccountGrantPolicy.may_receive(
            recipient_access=access,
            is_project_member=candidate.is_project_member,
            has_coherent_identity=candidate.has_coherent_identity,
        )
