import asyncio
from dataclasses import replace
from typing import override
from uuid import UUID

import pytest
from tests.support.authentication_evidence import MockAuthenticationEvidence

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.dtos.project_action_grant_dto import ProjectActionGrantDTO
from inframeld_backend.access.application.dtos.project_action_grants_page_facts_dto import (
    ProjectActionGrantsPageFactsDTO,
)
from inframeld_backend.access.application.protocols.project_action_grants_facts_reader import (
    ProjectActionGrantsFactsReader,
)
from inframeld_backend.access.application.queries.list_project_action_grants_query import (
    ListProjectActionGrantsQuery,
)
from inframeld_backend.access.application.services.project_action_grants_service import (
    ProjectActionGrantsService,
)
from inframeld_backend.access.application.value_objects.project_action_grants_cursor import (
    ProjectActionGrantsCursor,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    DependencyUnavailableError,
    InvalidInputError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

ORGANIZATION = OrganizationId(UUID(int=2))
PROJECT = ProjectId(UUID(int=3))
INSTALLATION = InstallationId(UUID(int=4))
ACTION = ActionId("create-access-groups")
ACTOR = Principal(
    PrincipalId(UUID(int=1)), ORGANIZATION, PrincipalKind.HUMAN, PrincipalStatus.ACTIVE
)
ACCESS = AccessContextDTO(ACTOR.id, MockAuthenticationEvidence.browser())
AUTHORITY = ProjectActionFactsDTO(ACTOR, False, None, ProjectStatus.ACTIVE, True, True)
ITEMS = tuple(
    ProjectActionGrantDTO(PrincipalId(UUID(int=i)), ACTION, i == 20) for i in (10, 20, 30)
)
FACTS = ProjectActionGrantsPageFactsDTO(
    INSTALLATION, ORGANIZATION, PROJECT, ACTION, AUTHORITY, True, ITEMS
)


class MockGrantFacts(ProjectActionGrantsFactsReader):
    def __init__(self, result: ProjectActionGrantsPageFactsDTO | None = FACTS) -> None:
        self.result = result
        self.calls: list[tuple[ProjectId, ActionId, PrincipalId | None, int]] = []
        self.error: BaseException | None = None

    @override
    async def read_page(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        action_id: ActionId,
        after: PrincipalId | None,
        limit: int,
    ) -> ProjectActionGrantsPageFactsDTO | None:
        assert access.actor_principal_id == ACCESS.actor_principal_id
        self.calls.append((project_id, action_id, after, limit))
        if self.error is not None:
            raise self.error
        return self.result


def _cursor(*, action: ActionId = ACTION, project: ProjectId = PROJECT) -> str:
    return ProjectActionGrantsCursor(
        INSTALLATION, ORGANIZATION, project, action, ITEMS[1].recipient_principal_id
    ).to_token()


@pytest.mark.asyncio
async def test_page_retains_stored_levels_and_uses_one_current_observation() -> None:
    facts = MockGrantFacts()
    page = await ProjectActionGrantsService(facts).list_grants(
        access=ACCESS, query=ListProjectActionGrantsQuery(PROJECT, ACTION, 2)
    )
    assert (page.project_id, page.action_id, page.items) == (PROJECT, ACTION, ITEMS[:2])
    assert page.next_cursor == _cursor()
    assert facts.calls == [(PROJECT, ACTION, None, 2)]


@pytest.mark.asyncio
async def test_continuation_is_fresh_and_empty_page_retains_authority_header() -> None:
    facts = MockGrantFacts(replace(FACTS, items=()))
    service = ProjectActionGrantsService(facts)
    query = ListProjectActionGrantsQuery(PROJECT, ACTION, 2, _cursor())
    page = await service.list_grants(access=ACCESS, query=query)
    assert page.items == () and page.next_cursor is None
    assert facts.calls == [(PROJECT, ACTION, ITEMS[1].recipient_principal_id, 2)]

    facts.result = replace(FACTS, actor_can_grant_action=False)
    with pytest.raises(AccessDeniedError):
        await service.list_grants(access=ACCESS, query=query)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "authority",
    [
        replace(AUTHORITY, has_exact_action_grant=False),
        replace(AUTHORITY, has_pending_recovery=True),
        replace(AUTHORITY, principal=replace(ACTOR, status=PrincipalStatus.SUSPENDED)),
    ],
)
async def test_ineligible_or_use_denied_actor_cannot_read(authority: ProjectActionFactsDTO) -> None:
    facts = MockGrantFacts(replace(FACTS, action=authority))
    with pytest.raises(AccessDeniedError):
        await ProjectActionGrantsService(facts).list_grants(
            access=ACCESS, query=ListProjectActionGrantsQuery(PROJECT, ACTION)
        )


@pytest.mark.asyncio
async def test_use_only_is_insufficient_even_when_assignment_page_is_empty() -> None:
    facts = MockGrantFacts(replace(FACTS, actor_can_grant_action=False, items=()))
    with pytest.raises(AccessDeniedError):
        await ProjectActionGrantsService(facts).list_grants(
            access=ACCESS, query=ListProjectActionGrantsQuery(PROJECT, ACTION)
        )


@pytest.mark.asyncio
async def test_verified_application_cannot_administer_even_with_a_stored_grant() -> None:
    access = AccessContextDTO(ACTOR.id, MockAuthenticationEvidence.application_key())
    facts = MockGrantFacts(
        replace(
            FACTS,
            action=replace(AUTHORITY, principal=replace(ACTOR, kind=PrincipalKind.APPLICATION)),
        )
    )
    with pytest.raises(AccessDeniedError):
        await ProjectActionGrantsService(facts).list_grants(
            access=access, query=ListProjectActionGrantsQuery(PROJECT, ACTION)
        )


@pytest.mark.asyncio
async def test_authentication_kind_mismatch_is_an_internal_contract_failure() -> None:
    facts = MockGrantFacts(
        replace(
            FACTS,
            action=replace(AUTHORITY, principal=replace(ACTOR, kind=PrincipalKind.APPLICATION)),
        )
    )
    with pytest.raises(RuntimeError, match="principal kind"):
        await ProjectActionGrantsService(facts).list_grants(
            access=ACCESS, query=ListProjectActionGrantsQuery(PROJECT, ACTION)
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "facts", [None, replace(FACTS, action=replace(AUTHORITY, is_project_member=False))]
)
async def test_missing_or_hidden_project_has_safe_not_found(
    facts: ProjectActionGrantsPageFactsDTO | None,
) -> None:
    with pytest.raises(ResourceNotFoundError):
        await ProjectActionGrantsService(MockGrantFacts(facts)).list_grants(
            access=ACCESS, query=ListProjectActionGrantsQuery(PROJECT, ACTION)
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("cursor", [_cursor.__name__])
async def test_malformed_cursor_is_safe_invalid_input(cursor: str) -> None:
    with pytest.raises(InvalidInputError):
        await ProjectActionGrantsService(MockGrantFacts()).list_grants(
            access=ACCESS, query=ListProjectActionGrantsQuery(PROJECT, ACTION, cursor=cursor)
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("other", [ActionId("manage-project-members"), ActionId("inspect-budget")])
async def test_cursor_cannot_cross_action(other: ActionId) -> None:
    with pytest.raises(InvalidInputError):
        await ProjectActionGrantsService(MockGrantFacts()).list_grants(
            access=ACCESS,
            query=ListProjectActionGrantsQuery(PROJECT, ACTION, cursor=_cursor(action=other)),
        )


@pytest.mark.asyncio
async def test_cursor_cannot_cross_project() -> None:
    with pytest.raises(InvalidInputError):
        await ProjectActionGrantsService(MockGrantFacts()).list_grants(
            access=ACCESS,
            query=ListProjectActionGrantsQuery(
                PROJECT, ACTION, cursor=_cursor(project=ProjectId(UUID(int=100)))
            ),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["build", "query", "unknown", "create-projects"])
async def test_only_fixed_project_actions_are_admitted(action: str) -> None:
    facts = MockGrantFacts()
    with pytest.raises(InvalidInputError):
        await ProjectActionGrantsService(facts).list_grants(
            access=ACCESS, query=ListProjectActionGrantsQuery(PROJECT, ActionId(action))
        )
    assert facts.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "items",
    [
        (ITEMS[1], ITEMS[0]),
        (ITEMS[0], ITEMS[0]),
        (replace(ITEMS[0], action_id=ActionId("query")),),
        ITEMS + ITEMS,
    ],
)
async def test_incoherent_page_is_not_disclosed(items: tuple[ProjectActionGrantDTO, ...]) -> None:
    with pytest.raises(RuntimeError):
        await ProjectActionGrantsService(MockGrantFacts(replace(FACTS, items=items))).list_grants(
            access=ACCESS, query=ListProjectActionGrantsQuery(PROJECT, ACTION, 2)
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [TimeoutError(), asyncio.CancelledError()])
async def test_dependency_timeout_maps_safely_and_cancellation_propagates(
    error: BaseException,
) -> None:
    facts = MockGrantFacts()
    facts.error = error
    expected = (
        DependencyUnavailableError if isinstance(error, TimeoutError) else asyncio.CancelledError
    )
    with pytest.raises(expected):
        await ProjectActionGrantsService(facts).list_grants(
            access=ACCESS, query=ListProjectActionGrantsQuery(PROJECT, ACTION)
        )
