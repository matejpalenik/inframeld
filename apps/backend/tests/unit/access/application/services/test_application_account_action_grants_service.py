from dataclasses import replace
from typing import override
from uuid import UUID

import pytest
from tests.support.authentication_evidence import MockAuthenticationEvidence

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_account_action_grant_dto import (
    ApplicationAccountActionGrantDTO,
)
from inframeld_backend.access.application.dtos.application_account_action_grants_page_facts_dto import (
    ApplicationAccountActionGrantsPageFactsDTO,
)
from inframeld_backend.access.application.dtos.application_account_grant_target_dto import (
    ApplicationAccountGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.human_credential_facts_dto import (
    HumanCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
)
from inframeld_backend.access.application.protocols.application_account_action_grants_facts_reader import (
    ApplicationAccountActionGrantsFactsReader,
)
from inframeld_backend.access.application.queries.list_application_account_action_grants_query import (
    ListApplicationAccountActionGrantsQuery,
)
from inframeld_backend.access.application.services.application_account_action_grants_service import (
    ApplicationAccountActionGrantsService,
)
from inframeld_backend.access.application.value_objects.access_action_grants_cursor import (
    AccessActionGrantsCursor,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    AuthenticationRequiredError,
    InvalidInputError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

ORG = OrganizationId(UUID(int=2))
PROJECT = ProjectId(UUID(int=3))
TARGET_ID = PrincipalId(UUID(int=4))
ACTOR = Principal(
    id=PrincipalId(UUID(int=1)),
    organization_id=ORG,
    kind=PrincipalKind.HUMAN,
    status=PrincipalStatus.ACTIVE,
)
ACCESS = AccessContextDTO(
    actor_principal_id=ACTOR.id, authentication_evidence=MockAuthenticationEvidence.browser()
)
ACTION = ActionId("issue-application-keys")
TARGET = ApplicationAccountGrantTargetDTO(project_id=PROJECT, application_principal_id=TARGET_ID)
ITEMS = tuple(
    ApplicationAccountActionGrantDTO(
        recipient_principal_id=PrincipalId(UUID(int=i)), action_id=ACTION, can_grant=i == 20
    )
    for i in (10, 20, 30)
)
FACTS = ApplicationAccountActionGrantsPageFactsDTO(
    installation_id=InstallationId(UUID(int=5)),
    organization_id=ORG,
    project_id=PROJECT,
    application_principal_id=TARGET_ID,
    action_id=ACTION,
    actor_can_grant=True,
    items=ITEMS,
    actor=ProjectActionFactsDTO(
        principal=ACTOR,
        has_pending_recovery=False,
        oauth_credential_facts=HumanCredentialFactsDTO(True, HumanCredentialVersion(1)),
        project_status=ProjectStatus.ACTIVE,
        is_project_member=True,
        has_exact_action_grant=True,
    ),
)


class MockGrantFacts(ApplicationAccountActionGrantsFactsReader):
    def __init__(self, facts: ApplicationAccountActionGrantsPageFactsDTO | None = FACTS) -> None:
        self.facts = facts
        self.calls: list[tuple[PrincipalId | None, int]] = []

    @override
    async def read_page(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        application_principal_id: PrincipalId,
        action_id: ActionId,
        after: PrincipalId | None,
        limit: int,
    ) -> ApplicationAccountActionGrantsPageFactsDTO | None:
        self.calls.append((after, limit))
        return self.facts


def _query(*, cursor: str | None = None) -> ListApplicationAccountActionGrantsQuery:
    return ListApplicationAccountActionGrantsQuery(
        project_id=PROJECT,
        application_principal_id=TARGET_ID,
        action_id=ACTION,
        limit=2,
        cursor=cursor,
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
    page = await ApplicationAccountActionGrantsService(facts).list_grants(
        access=ACCESS, query=_query()
    )
    assert page.items == ITEMS[:2] and page.action_id == ACTION
    assert page.application_principal_id == TARGET_ID
    assert page.next_cursor == _cursor()
    assert facts.calls == [(None, 2)]


@pytest.mark.asyncio
async def test_empty_continuation_still_requires_current_delegation() -> None:
    facts = MockGrantFacts(replace(FACTS, items=()))
    service = ApplicationAccountActionGrantsService(facts)
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
        await ApplicationAccountActionGrantsService(MockGrantFacts()).list_grants(
            access=ACCESS, query=_query(cursor=cursor.to_token())
        )


@pytest.mark.asyncio
async def test_missing_scope_is_not_an_empty_successful_page() -> None:
    with pytest.raises(ResourceNotFoundError):
        await ApplicationAccountActionGrantsService(MockGrantFacts(None)).list_grants(
            access=ACCESS, query=_query()
        )


@pytest.mark.asyncio
async def test_recovery_block_denies_even_with_exact_stored_delegation() -> None:
    blocked = replace(FACTS, actor=replace(FACTS.actor, has_pending_recovery=True))
    with pytest.raises(AccessDeniedError):
        await ApplicationAccountActionGrantsService(MockGrantFacts(blocked)).list_grants(
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
            await ApplicationAccountActionGrantsService(
                MockGrantFacts(replace(FACTS, items=items))
            ).list_grants(access=ACCESS, query=_query())


@pytest.mark.asyncio
@pytest.mark.parametrize("oauth", [False, True])
async def test_browser_currentness_preserves_the_presented_credential_family(oauth: bool) -> None:
    """Reject stale evidence before disclosing data, recovering originals or changing authority."""
    evidence = (
        MockAuthenticationEvidence.human_oauth() if oauth else MockAuthenticationEvidence.browser()
    )
    stale = HumanCredentialFactsDTO(True, HumanCredentialVersion(2))
    expected = HumanOAuthCredentialRejectedError if oauth else AuthenticationRequiredError
    facts = MockGrantFacts(replace(FACTS, actor=replace(FACTS.actor, oauth_credential_facts=stale)))
    with pytest.raises(AuthenticationRequiredError) as caught:
        await ApplicationAccountActionGrantsService(facts).list_grants(
            access=replace(ACCESS, authentication_evidence=evidence), query=_query()
        )
    assert type(caught.value) is expected
    assert facts.calls == [(None, 2)]
