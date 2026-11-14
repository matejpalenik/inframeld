"""Authorize one concrete eligible-recipient directory without hiding post-limit mistakes."""

from dataclasses import replace
from typing import override
from uuid import UUID

import pytest
from tests.support.authentication_evidence import MockAuthenticationEvidence

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
from inframeld_backend.access.application.dtos.grant_recipients_page_facts_dto import (
    GrantRecipientsPageFactsDTO,
)
from inframeld_backend.access.application.dtos.human_credential_facts_dto import (
    HumanCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.model_connection_grant_target_dto import (
    ModelConnectionGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.dtos.project_grant_target_dto import ProjectGrantTargetDTO
from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
)
from inframeld_backend.access.application.protocols.grant_recipients_facts_reader import (
    GrantRecipientsFactsReader,
)
from inframeld_backend.access.application.queries.list_project_grant_recipients_query import (
    ListProjectGrantRecipientsQuery,
)
from inframeld_backend.access.application.services.project_grant_recipients_service import (
    ProjectGrantRecipientsService,
)
from inframeld_backend.access.application.value_objects.grant_recipients_cursor import (
    GrantRecipientsCursor,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.access_group_relationships import (
    AccessGroupRelationships,
)
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
TARGET = AccessGroupGrantTargetDTO(project_id=PROJECT, access_group_id=AccessGroupId(UUID(int=4)))
ACTION = ActionId("add-documents")
ACTOR = Principal(
    id=PrincipalId(UUID(int=1)),
    organization_id=ORG,
    kind=PrincipalKind.HUMAN,
    status=PrincipalStatus.ACTIVE,
)
ACCESS = AccessContextDTO(
    actor_principal_id=ACTOR.id, authentication_evidence=MockAuthenticationEvidence.browser()
)
HUMAN = GrantRecipientCandidateDTO(
    principal=replace(ACTOR, id=PrincipalId(UUID(int=10))),
    display_name="Bob",
    is_project_member=True,
    has_pending_recovery=False,
    has_coherent_identity=True,
    application_is_project_bound=False,
)
APPLICATION = GrantRecipientCandidateDTO(
    principal=replace(ACTOR, id=PrincipalId(UUID(int=20)), kind=PrincipalKind.APPLICATION),
    display_name="SupportBot",
    is_project_member=True,
    has_pending_recovery=False,
    has_coherent_identity=False,
    application_is_project_bound=True,
)
FACTS = GrantRecipientsPageFactsDTO(
    installation_id=InstallationId(UUID(int=5)),
    organization_id=ORG,
    project_id=PROJECT,
    target=TARGET,
    action_id=ACTION,
    actor=ProjectActionFactsDTO(
        principal=ACTOR,
        has_pending_recovery=False,
        oauth_credential_facts=HumanCredentialFactsDTO(True, HumanCredentialVersion(1)),
        project_status=ProjectStatus.ACTIVE,
        is_project_member=True,
        has_exact_action_grant=False,
    ),
    actor_can_grant=False,
    actor_group_relationships=AccessGroupRelationships(member=True, manager=True),
    items=(HUMAN, APPLICATION),
)


class MockRecipientsFacts(GrantRecipientsFactsReader):
    def __init__(self, facts: GrantRecipientsPageFactsDTO | None = FACTS) -> None:
        self.facts = facts
        self.calls: list[tuple[tuple[PrincipalKind, ...], PrincipalId | None, int]] = []

    @override
    async def read_page(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        target: ProjectGrantTargetDTO
        | AccessGroupGrantTargetDTO
        | ApplicationAccountGrantTargetDTO
        | ModelConnectionGrantTargetDTO,
        action_id: ActionId,
        eligible_kinds: tuple[PrincipalKind, ...],
        after: PrincipalId | None,
        limit: int,
    ) -> GrantRecipientsPageFactsDTO | None:
        self.calls.append((eligible_kinds, after, limit))
        return self.facts


def _query(*, cursor: str | None = None) -> ListProjectGrantRecipientsQuery:
    return ListProjectGrantRecipientsQuery(
        project_id=PROJECT, target=TARGET, action_id=ACTION, limit=1, cursor=cursor
    )


@pytest.mark.asyncio
async def test_same_group_manager_reads_only_safe_bounded_eligible_choices() -> None:
    facts = MockRecipientsFacts()
    page = await ProjectGrantRecipientsService(facts).list_recipients(access=ACCESS, query=_query())
    assert [(item.principal_id, item.display_name, item.kind) for item in page.items] == [
        (HUMAN.principal.id, "Bob", PrincipalKind.HUMAN)
    ]
    assert page.next_cursor is not None
    cursor = GrantRecipientsCursor.from_token(page.next_cursor)
    assert (
        cursor.target == TARGET
        and cursor.action_id == ACTION
        and cursor.after == HUMAN.principal.id
    )
    assert facts.calls == [((PrincipalKind.HUMAN, PrincipalKind.APPLICATION), None, 1)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "target,action,kinds",
    [
        (
            ProjectGrantTargetDTO(project_id=PROJECT),
            "inspect-budget",
            (PrincipalKind.HUMAN, PrincipalKind.APPLICATION),
        ),
        (ProjectGrantTargetDTO(project_id=PROJECT), "manage-budget", (PrincipalKind.HUMAN,)),
        (
            ApplicationAccountGrantTargetDTO(
                project_id=PROJECT, application_principal_id=PrincipalId(UUID(int=30))
            ),
            "issue-application-keys",
            (PrincipalKind.HUMAN,),
        ),
    ],
)
async def test_existing_catalogue_supplies_eligible_kinds_before_the_reader_limit(
    target: ProjectGrantTargetDTO
    | AccessGroupGrantTargetDTO
    | ApplicationAccountGrantTargetDTO
    | ModelConnectionGrantTargetDTO,
    action: str,
    kinds: tuple[PrincipalKind, ...],
) -> None:
    query = ListProjectGrantRecipientsQuery(
        project_id=PROJECT, target=target, action_id=ActionId(action)
    )
    facts = MockRecipientsFacts(
        replace(
            FACTS,
            target=target,
            action_id=query.action_id,
            actor_can_grant=True,
            actor_group_relationships=None,
            items=(HUMAN,),
        )
    )
    page = await ProjectGrantRecipientsService(facts).list_recipients(access=ACCESS, query=query)
    assert page.items[0].principal_id == HUMAN.principal.id
    assert facts.calls == [(kinds, None, 25)]


@pytest.mark.asyncio
async def test_empty_page_is_not_authority_for_use_only_or_recovery_blocked_callers() -> None:
    for facts in [
        replace(
            FACTS,
            actor_group_relationships=AccessGroupRelationships(member=True, manager=False),
            items=(),
        ),
        replace(FACTS, actor=replace(FACTS.actor, has_pending_recovery=True), items=()),
    ]:
        with pytest.raises(AccessDeniedError):
            await ProjectGrantRecipientsService(MockRecipientsFacts(facts)).list_recipients(
                access=ACCESS, query=_query()
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "candidate",
    [
        replace(HUMAN, is_project_member=False),
        replace(HUMAN, has_pending_recovery=True),
        replace(HUMAN, has_coherent_identity=False),
        replace(HUMAN, principal=replace(HUMAN.principal, status=PrincipalStatus.SUSPENDED)),
        replace(APPLICATION, application_is_project_bound=False),
        replace(
            HUMAN, principal=replace(HUMAN.principal, organization_id=OrganizationId(UUID(int=99)))
        ),
    ],
)
async def test_bad_prefilter_observations_fail_closed_instead_of_post_limit_filtering(
    candidate: GrantRecipientCandidateDTO,
) -> None:
    with pytest.raises(RuntimeError):
        await ProjectGrantRecipientsService(
            MockRecipientsFacts(replace(FACTS, items=(candidate,)))
        ).list_recipients(access=ACCESS, query=_query())


@pytest.mark.asyncio
async def test_missing_authoritative_scope_is_not_an_empty_directory() -> None:
    with pytest.raises(ResourceNotFoundError):
        await ProjectGrantRecipientsService(MockRecipientsFacts(None)).list_recipients(
            access=ACCESS, query=_query()
        )


@pytest.mark.asyncio
async def test_malformed_continuation_is_not_a_new_first_page() -> None:
    with pytest.raises(InvalidInputError):
        await ProjectGrantRecipientsService(MockRecipientsFacts()).list_recipients(
            access=ACCESS, query=_query(cursor="not-a-cursor")
        )


@pytest.mark.asyncio
async def test_authorized_empty_continuation_still_rechecks_current_management() -> None:
    cursor = GrantRecipientsCursor(
        installation_id=FACTS.installation_id,
        organization_id=ORG,
        target=TARGET,
        action_id=ACTION,
        after=APPLICATION.principal.id,
    ).to_token()
    facts = MockRecipientsFacts(replace(FACTS, items=()))
    service = ProjectGrantRecipientsService(facts)
    page = await service.list_recipients(access=ACCESS, query=_query(cursor=cursor))
    assert page.items == () and page.next_cursor is None
    assert facts.calls == [
        ((PrincipalKind.HUMAN, PrincipalKind.APPLICATION), APPLICATION.principal.id, 1)
    ]
    facts.facts = replace(
        FACTS,
        items=(),
        actor_group_relationships=AccessGroupRelationships(member=True, manager=False),
    )
    with pytest.raises(AccessDeniedError):
        await service.list_recipients(access=ACCESS, query=_query(cursor=cursor))


@pytest.mark.asyncio
@pytest.mark.parametrize("oauth", [False, True])
async def test_browser_currentness_preserves_the_presented_credential_family(oauth: bool) -> None:
    """Reject stale evidence before disclosing data, recovering originals or changing authority."""
    evidence = (
        MockAuthenticationEvidence.human_oauth() if oauth else MockAuthenticationEvidence.browser()
    )
    stale = HumanCredentialFactsDTO(True, HumanCredentialVersion(2))
    expected = HumanOAuthCredentialRejectedError if oauth else AuthenticationRequiredError
    reader = MockRecipientsFacts(
        replace(FACTS, actor=replace(FACTS.actor, oauth_credential_facts=stale))
    )
    with pytest.raises(AuthenticationRequiredError) as caught:
        await ProjectGrantRecipientsService(reader).list_recipients(
            access=replace(ACCESS, authentication_evidence=evidence), query=_query()
        )
    assert type(caught.value) is expected
    assert reader.calls == [((PrincipalKind.HUMAN, PrincipalKind.APPLICATION), None, 1)]
