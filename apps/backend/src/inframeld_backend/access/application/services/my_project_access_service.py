import asyncio
from typing import override

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.access_group_grant_target_dto import (
    AccessGroupGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.my_project_access_grant_dto import (
    MyProjectAccessGrantDTO,
)
from inframeld_backend.access.application.dtos.my_project_access_page_dto import (
    MyProjectAccessPageDTO,
)
from inframeld_backend.access.application.dtos.my_project_access_relationship_dto import (
    MyProjectAccessRelationshipDTO,
)
from inframeld_backend.access.application.dtos.project_grant_target_dto import ProjectGrantTargetDTO
from inframeld_backend.access.application.enums.my_project_access_item_kind import (
    MyProjectAccessItemKind,
)
from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
)
from inframeld_backend.access.application.protocols.my_project_access_facts_reader import (
    MyProjectAccessFactsReader,
)
from inframeld_backend.access.application.protocols.my_project_access_reader import (
    MyProjectAccessReader,
)
from inframeld_backend.access.application.queries.get_my_project_access_query import (
    GetMyProjectAccessQuery,
)
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.application.value_objects.my_project_access_cursor import (
    MyProjectAccessCursor,
)
from inframeld_backend.access.application.value_objects.my_project_access_position import (
    MyProjectAccessPosition,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
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
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


def _position(
    item: MyProjectAccessGrantDTO | MyProjectAccessRelationshipDTO,
) -> MyProjectAccessPosition:
    """Carry the item's stable combined-page order into the next cursor without granting access."""
    if isinstance(item, MyProjectAccessRelationshipDTO):
        return MyProjectAccessPosition(item.kind, item.access_group_id.value, None)

    target = item.target
    if isinstance(target, ProjectGrantTargetDTO):
        target_id = target.project_id.value
    elif isinstance(target, AccessGroupGrantTargetDTO):
        target_id = target.access_group_id.value
    else:
        target_id = target.application_principal_id.value
    return MyProjectAccessPosition(MyProjectAccessItemKind.GRANT, target_id, item.action_id)


class MyProjectAccessService(MyProjectAccessReader):
    def __init__(self, project_access_facts_reader: MyProjectAccessFactsReader) -> None:
        self._project_access_facts_reader = project_access_facts_reader

    @override
    async def get_access(
        self, *, access: AccessContextDTO, query: GetMyProjectAccessQuery
    ) -> MyProjectAccessPageDTO:
        try:
            cursor = MyProjectAccessCursor.from_token(query.cursor) if query.cursor else None
        except ValueError as error:
            raise InvalidInputError(
                "The continuation cursor is invalid or incompatible."
            ) from error

        try:
            async with asyncio.timeout(5):
                facts = await self._project_access_facts_reader.read_page(
                    access=access,
                    project_id=query.project_id,
                    after=cursor.after if cursor is not None else None,
                    limit=query.limit,
                )
        except TimeoutError as error:
            raise DependencyUnavailableError() from error
        if facts is None:
            raise ResourceNotFoundError()
        if (
            facts.project_id != query.project_id
            or facts.actor.id != access.actor_principal_id
            or facts.actor.organization_id != facts.organization_id
            or type(facts.access_revision) is not int
            or not 0 <= facts.access_revision <= RevisionValidation.MAX_VALUE
        ):
            raise RuntimeError("The own-access observation changed actor, scope or revision.")

        PrincipalAccessEvaluationService.require_human(access=access, principal=facts.actor)
        eligibility = PrincipalAccessEvaluationService.evaluate(
            access=access,
            principal=facts.actor,
            has_pending_recovery=facts.has_pending_recovery,
            oauth_credential_facts=facts.oauth_credential_facts,
        )
        if not eligibility.credential_is_current:
            raise HumanOAuthCredentialRejectedError()
        if facts.actor.kind is not PrincipalKind.HUMAN or not PrincipalAccessPolicy.may_use_product(
            eligibility
        ):
            raise AccessDeniedError()
        if not ProjectVisibilityPolicy.may_view_project(
            principal_status=facts.actor.status,
            project_status=facts.project_status,
            is_project_member=facts.is_project_member,
        ):
            raise ResourceNotFoundError()

        if cursor is not None and (
            cursor.installation_id,
            cursor.organization_id,
            cursor.project_id,
            cursor.principal_id,
        ) != (facts.installation_id, facts.organization_id, facts.project_id, facts.actor.id):
            raise InvalidInputError("The continuation cursor is invalid or incompatible.")
        if len(facts.items) > query.limit + 1:
            raise RuntimeError("The own-access observation exceeded its combined page bound.")

        previous = cursor.after.sort_key if cursor is not None else None
        for item in facts.items:
            project = (
                item.target.project_id
                if isinstance(item, MyProjectAccessGrantDTO)
                else item.project_id
            )
            if project != facts.project_id:
                raise RuntimeError("An own-access relationship belongs to another Project.")
            current = _position(item).sort_key
            if previous is not None and current <= previous:
                raise RuntimeError(
                    "The own-access observation violated combined order or position."
                )
            previous = current

        items = facts.items[: query.limit]
        continuation = (
            MyProjectAccessCursor(
                facts.installation_id,
                facts.organization_id,
                facts.project_id,
                facts.actor.id,
                _position(items[-1]),
            ).to_token()
            if len(facts.items) > query.limit
            else None
        )
        grants = tuple(item for item in items if isinstance(item, MyProjectAccessGrantDTO))
        memberships = tuple(
            item.access_group_id
            for item in items
            if isinstance(item, MyProjectAccessRelationshipDTO) and item.kind == "membership"
        )
        managements = tuple(
            item.access_group_id
            for item in items
            if isinstance(item, MyProjectAccessRelationshipDTO) and item.kind == "management"
        )
        return MyProjectAccessPageDTO(
            project_id=facts.project_id,
            principal_id=facts.actor.id,
            access_revision=facts.access_revision,
            grants=grants,
            group_memberships=memberships,
            group_managements=managements,
            next_cursor=continuation,
        )
