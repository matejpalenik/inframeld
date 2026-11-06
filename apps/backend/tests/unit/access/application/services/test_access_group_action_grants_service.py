from dataclasses import replace
from typing import override
from uuid import UUID

import pytest
from tests.support.authentication_evidence import MockAuthenticationEvidence

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.access_group_action_grant_dto import (
    AccessGroupActionGrantDTO,
)
from inframeld_backend.access.application.dtos.access_group_action_grants_page_facts_dto import (
    AccessGroupActionGrantsPageFactsDTO,
)
from inframeld_backend.access.application.dtos.access_group_grant_target_dto import (
    AccessGroupGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.protocols.access_group_action_grants_facts_reader import (
    AccessGroupActionGrantsFactsReader,
)
from inframeld_backend.access.application.queries.list_access_group_action_grants_query import (
    ListAccessGroupActionGrantsQuery,
)
from inframeld_backend.access.application.services.access_group_action_grants_service import (
    AccessGroupActionGrantsService,
)
from inframeld_backend.access.application.value_objects.access_action_grants_cursor import (
    AccessActionGrantsCursor,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    InvalidInputError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

ORG = OrganizationId(UUID(int=2))
PROJECT = ProjectId(UUID(int=3))
TARGET_ID = AccessGroupId(UUID(int=4))
ACTOR = Principal(
    id=PrincipalId(UUID(int=1)),
    organization_id=ORG,
    kind=PrincipalKind.HUMAN,
    status=PrincipalStatus.ACTIVE,
)
ACCESS = AccessContextDTO(
    actor_principal_id=ACTOR.id, authentication_evidence=MockAuthenticationEvidence.browser()
)
ACTION = ActionId("add-documents")
TARGET = AccessGroupGrantTargetDTO(project_id=PROJECT, access_group_id=TARGET_ID)
ITEMS = tuple(
    AccessGroupActionGrantDTO(
        recipient_principal_id=PrincipalId(UUID(int=i)), action_id=ACTION, can_grant=i == 20
    )
    for i in (10, 20, 30)
)
FACTS = AccessGroupActionGrantsPageFactsDTO(
    installation_id=InstallationId(UUID(int=5)),
    organization_id=ORG,
    project_id=PROJECT,
    group_id=TARGET_ID,
    action_id=ACTION,
    actor_can_grant=True,
    items=ITEMS,
    actor=ProjectActionFactsDTO(
        principal=ACTOR,
        has_pending_recovery=False,
        oauth_credential_facts=None,
        project_status=ProjectStatus.ACTIVE,
        is_project_member=True,
        has_exact_action_grant=True,
    ),
    actor_is_group_member=False,
    actor_is_group_manager=False,
)


class MockGrantFacts(AccessGroupActionGrantsFactsReader):
    def __init__(self, facts: AccessGroupActionGrantsPageFactsDTO | None = FACTS) -> None:
        self.facts = facts
        self.calls: list[tuple[PrincipalId | None, int]] = []

    @override
    async def read_page(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        group_id: AccessGroupId,
        action_id: ActionId,
        after: PrincipalId | None,
        limit: int,
    ) -> AccessGroupActionGrantsPageFactsDTO | None:
        self.calls.append((after, limit))
        return self.facts


def _query(*, cursor: str | None = None) -> ListAccessGroupActionGrantsQuery:
    return ListAccessGroupActionGrantsQuery(
        project_id=PROJECT, group_id=TARGET_ID, action_id=ACTION, limit=2, cursor=cursor
    )


def _cursor() -> str:
    return AccessActionGrantsCursor(
        installation_id=FACTS.installation_id,
        organization_id=ORG,
        target=TARGET,
        action_id=ACTION,
        after=ITEMS[1].recipient_principal_id,
    ).to_token()


@pytest.mark.asyncio
async def test_page_keeps_exact_stored_levels_and_bounded_position() -> None:
    facts = MockGrantFacts()
    page = await AccessGroupActionGrantsService(facts).list_grants(access=ACCESS, query=_query())
    assert page.items == ITEMS[:2] and page.action_id == ACTION
    assert page.group_id == TARGET_ID
    assert page.next_cursor == _cursor()
    assert facts.calls == [(None, 2)]


@pytest.mark.asyncio
async def test_empty_continuation_still_requires_current_delegation() -> None:
    facts = MockGrantFacts(replace(FACTS, items=()))
    service = AccessGroupActionGrantsService(facts)
    page = await service.list_grants(access=ACCESS, query=_query(cursor=_cursor()))
    assert page.items == () and page.next_cursor is None
    assert facts.calls == [(ITEMS[1].recipient_principal_id, 2)]
    facts.facts = replace(FACTS, actor_can_grant=False, items=())
    with pytest.raises(AccessDeniedError):
        await service.list_grants(access=ACCESS, query=_query(cursor=_cursor()))


@pytest.mark.asyncio
async def test_cursor_cannot_cross_the_exact_action() -> None:
    cursor = replace(
        AccessActionGrantsCursor.from_token(_cursor()), action_id=ActionId("other-action")
    )
    with pytest.raises(InvalidInputError):
        await AccessGroupActionGrantsService(MockGrantFacts()).list_grants(
            access=ACCESS, query=_query(cursor=cursor.to_token())
        )


@pytest.mark.asyncio
async def test_missing_scope_is_not_an_empty_successful_page() -> None:
    with pytest.raises(ResourceNotFoundError):
        await AccessGroupActionGrantsService(MockGrantFacts(None)).list_grants(
            access=ACCESS, query=_query()
        )


@pytest.mark.asyncio
async def test_recovery_block_denies_even_with_exact_stored_delegation() -> None:
    blocked = replace(FACTS, actor=replace(FACTS.actor, has_pending_recovery=True))
    with pytest.raises(AccessDeniedError):
        await AccessGroupActionGrantsService(MockGrantFacts(blocked)).list_grants(
            access=ACCESS, query=_query()
        )


@pytest.mark.asyncio
async def test_reader_cannot_change_assignment_action_or_uuid_order() -> None:
    for items in [
        (ITEMS[1], ITEMS[0]),
        (replace(ITEMS[0], action_id=ActionId("other")),),
        ITEMS + ITEMS,
    ]:
        with pytest.raises(RuntimeError):
            await AccessGroupActionGrantsService(
                MockGrantFacts(replace(FACTS, items=items))
            ).list_grants(access=ACCESS, query=_query())


@pytest.mark.asyncio
async def test_current_same_group_manager_may_list_without_direct_delegation() -> None:
    facts = replace(
        FACTS,
        actor_can_grant=False,
        actor_is_group_member=True,
        actor_is_group_manager=True,
        actor=replace(FACTS.actor, has_exact_action_grant=False),
    )
    page = await AccessGroupActionGrantsService(MockGrantFacts(facts)).list_grants(
        access=ACCESS, query=_query()
    )
    assert page.items == ITEMS[:2]
    with pytest.raises(AccessDeniedError):
        await AccessGroupActionGrantsService(
            MockGrantFacts(replace(facts, actor_is_group_member=False))
        ).list_grants(access=ACCESS, query=_query())
