import asyncio
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
from inframeld_backend.access.application.dtos.human_oauth_credential_facts_dto import (
    HumanOAuthCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.my_project_access_facts_dto import (
    MyProjectAccessFactsDTO,
)
from inframeld_backend.access.application.dtos.my_project_access_grant_dto import (
    MyProjectAccessGrantDTO,
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
from inframeld_backend.access.application.queries.get_my_project_access_query import (
    GetMyProjectAccessQuery,
)
from inframeld_backend.access.application.services.my_project_access_service import (
    MyProjectAccessService,
)
from inframeld_backend.access.application.value_objects.my_project_access_cursor import (
    MyProjectAccessCursor,
)
from inframeld_backend.access.application.value_objects.my_project_access_position import (
    MyProjectAccessPosition,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
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

INSTALLATION = InstallationId(UUID(int=1))
ORGANIZATION = OrganizationId(UUID(int=2))
PROJECT = ProjectId(UUID(int=3))
ACTOR = Principal(
    PrincipalId(UUID(int=4)), ORGANIZATION, PrincipalKind.HUMAN, PrincipalStatus.ACTIVE
)
ACCESS = AccessContextDTO(ACTOR.id, MockAuthenticationEvidence.browser())
GROUP = AccessGroupId(UUID(int=5))
APP = PrincipalId(UUID(int=6))
GRANTS = (
    MyProjectAccessGrantDTO(ProjectGrantTargetDTO(PROJECT), ActionId("inspect-budget"), False),
    MyProjectAccessGrantDTO(
        AccessGroupGrantTargetDTO(PROJECT, GROUP), ActionId("add-documents"), False
    ),
    MyProjectAccessGrantDTO(
        ApplicationAccountGrantTargetDTO(PROJECT, APP), ActionId("revoke-application-keys"), True
    ),
)
MEMBERSHIP = MyProjectAccessRelationshipDTO(MyProjectAccessItemKind.MEMBERSHIP, PROJECT, GROUP)
MANAGEMENT = MyProjectAccessRelationshipDTO(MyProjectAccessItemKind.MANAGEMENT, PROJECT, GROUP)
FACTS = MyProjectAccessFactsDTO(
    installation_id=INSTALLATION,
    organization_id=ORGANIZATION,
    project_id=PROJECT,
    access_revision=7,
    actor=ACTOR,
    has_pending_recovery=False,
    oauth_credential_facts=None,
    project_status=ProjectStatus.ACTIVE,
    is_project_member=True,
    items=(*GRANTS, MEMBERSHIP, MANAGEMENT),
)


class MockOwnAccessFacts(MyProjectAccessFactsReader):
    def __init__(self, result: MyProjectAccessFactsDTO | None = FACTS) -> None:
        self.result = result
        self.error: BaseException | None = None
        self.calls: list[tuple[PrincipalId, ProjectId, MyProjectAccessPosition | None, int]] = []

    @override
    async def read_page(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        after: MyProjectAccessPosition | None,
        limit: int,
    ) -> MyProjectAccessFactsDTO | None:
        self.calls.append((access.actor_principal_id, project_id, after, limit))
        if self.error is not None:
            raise self.error
        return self.result


def _cursor() -> MyProjectAccessCursor:
    return MyProjectAccessCursor(
        INSTALLATION,
        ORGANIZATION,
        PROJECT,
        ACTOR.id,
        MyProjectAccessPosition(MyProjectAccessItemKind.MEMBERSHIP, GROUP.value, None),
    )


@pytest.mark.asyncio
async def test_combined_limit_covers_all_three_grant_targets_and_group_relationships() -> None:
    facts = MockOwnAccessFacts()
    page = await MyProjectAccessService(facts).get_access(
        access=ACCESS, query=GetMyProjectAccessQuery(PROJECT, 4)
    )
    assert (page.project_id, page.principal_id, page.access_revision) == (PROJECT, ACTOR.id, 7)
    assert page.grants == GRANTS
    assert page.group_memberships == (GROUP,) and page.group_managements == ()
    assert MyProjectAccessCursor.from_token(page.next_cursor or "") == _cursor()
    assert facts.calls == [(ACTOR.id, PROJECT, None, 4)]


@pytest.mark.asyncio
async def test_eligible_member_with_no_action_grants_can_read_current_own_revision() -> None:
    facts = MockOwnAccessFacts(replace(FACTS, items=()))
    page = await MyProjectAccessService(facts).get_access(
        access=ACCESS, query=GetMyProjectAccessQuery(PROJECT)
    )
    assert (page.access_revision, page.grants, page.group_memberships, page.group_managements) == (
        7,
        (),
        (),
        (),
    )
    assert page.next_cursor is None


@pytest.mark.asyncio
async def test_full_page_partitions_actual_membership_and_management_without_extra_grants() -> None:
    page = await MyProjectAccessService(MockOwnAccessFacts()).get_access(
        access=ACCESS, query=GetMyProjectAccessQuery(PROJECT)
    )
    assert page.grants == GRANTS
    assert page.group_memberships == page.group_managements == (GROUP,)
    assert page.next_cursor is None


@pytest.mark.asyncio
async def test_current_oauth_evidence_is_rechecked_without_membership_management_authority() -> (
    None
):
    access = AccessContextDTO(ACTOR.id, MockAuthenticationEvidence.human_oauth())
    facts = MockOwnAccessFacts(
        replace(
            FACTS,
            items=(),
            oauth_credential_facts=HumanOAuthCredentialFactsDTO(True, HumanCredentialVersion(1)),
        )
    )
    service = MyProjectAccessService(facts)
    page = await service.get_access(access=access, query=GetMyProjectAccessQuery(PROJECT))
    assert page.principal_id == ACTOR.id and page.access_revision == 7

    facts.result = replace(
        FACTS,
        items=(),
        oauth_credential_facts=HumanOAuthCredentialFactsDTO(True, HumanCredentialVersion(2)),
    )
    with pytest.raises(HumanOAuthCredentialRejectedError):
        await service.get_access(access=access, query=GetMyProjectAccessQuery(PROJECT))


@pytest.mark.asyncio
async def test_continuation_reports_fresh_revision_and_authority_even_when_empty() -> None:
    facts = MockOwnAccessFacts(replace(FACTS, access_revision=8, items=()))
    query = GetMyProjectAccessQuery(PROJECT, 4, _cursor().to_token())
    service = MyProjectAccessService(facts)
    page = await service.get_access(access=ACCESS, query=query)
    assert page.access_revision == 8 and page.next_cursor is None
    assert facts.calls == [(ACTOR.id, PROJECT, _cursor().after, 4)]

    facts.result = replace(FACTS, items=(), has_pending_recovery=True)
    with pytest.raises(AccessDeniedError):
        await service.get_access(access=ACCESS, query=query)


@pytest.mark.asyncio
@pytest.mark.parametrize("binding", ["installation", "organization", "project", "principal"])
async def test_cursor_cannot_move_to_another_scope_or_person(binding: str) -> None:
    cursor = _cursor()
    if binding == "installation":
        cursor = replace(cursor, installation_id=InstallationId(UUID(int=90)))
    elif binding == "organization":
        cursor = replace(cursor, organization_id=OrganizationId(UUID(int=90)))
    elif binding == "project":
        cursor = replace(cursor, project_id=ProjectId(UUID(int=90)))
    else:
        cursor = replace(cursor, principal_id=PrincipalId(UUID(int=90)))
    with pytest.raises(InvalidInputError):
        await MyProjectAccessService(MockOwnAccessFacts()).get_access(
            access=ACCESS, query=GetMyProjectAccessQuery(PROJECT, cursor=cursor.to_token())
        )


@pytest.mark.asyncio
async def test_malformed_cursor_is_rejected_before_fact_disclosure() -> None:
    facts = MockOwnAccessFacts()
    with pytest.raises(InvalidInputError):
        await MyProjectAccessService(facts).get_access(
            access=ACCESS, query=GetMyProjectAccessQuery(PROJECT, cursor="not_valid")
        )
    assert facts.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("facts", [None, replace(FACTS, is_project_member=False)])
async def test_missing_or_hidden_project_is_not_an_empty_success(
    facts: MyProjectAccessFactsDTO | None,
) -> None:
    with pytest.raises(ResourceNotFoundError):
        await MyProjectAccessService(MockOwnAccessFacts(facts)).get_access(
            access=ACCESS, query=GetMyProjectAccessQuery(PROJECT)
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "facts",
    [
        replace(FACTS, has_pending_recovery=True),
        replace(FACTS, actor=replace(ACTOR, status=PrincipalStatus.SUSPENDED)),
    ],
)
async def test_ineligible_human_cannot_read_own_permissions(facts: MyProjectAccessFactsDTO) -> None:
    with pytest.raises(AccessDeniedError):
        await MyProjectAccessService(MockOwnAccessFacts(facts)).get_access(
            access=ACCESS, query=GetMyProjectAccessQuery(PROJECT)
        )


@pytest.mark.asyncio
async def test_verified_application_cannot_read_the_human_own_access_operation() -> None:
    facts = replace(FACTS, actor=replace(ACTOR, kind=PrincipalKind.APPLICATION))
    access = AccessContextDTO(ACTOR.id, MockAuthenticationEvidence.application_key())
    with pytest.raises(AccessDeniedError):
        await MyProjectAccessService(MockOwnAccessFacts(facts)).get_access(
            access=access, query=GetMyProjectAccessQuery(PROJECT)
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "facts",
    [
        replace(FACTS, actor=replace(ACTOR, id=PrincipalId(UUID(int=90)))),
        replace(FACTS, organization_id=OrganizationId(UUID(int=90))),
        replace(FACTS, project_id=ProjectId(UUID(int=90))),
        replace(FACTS, access_revision=-1),
        replace(FACTS, access_revision=True),
        replace(FACTS, access_revision=2**53),
    ],
)
async def test_reader_cannot_substitute_actor_scope_or_an_invalid_revision(
    facts: MyProjectAccessFactsDTO,
) -> None:
    with pytest.raises(RuntimeError):
        await MyProjectAccessService(MockOwnAccessFacts(facts)).get_access(
            access=ACCESS, query=GetMyProjectAccessQuery(PROJECT)
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "items",
    [
        (GRANTS[0], GRANTS[0]),
        (GRANTS[1], GRANTS[0]),
        (replace(GRANTS[0], target=ProjectGrantTargetDTO(ProjectId(UUID(int=90)))),),
        (replace(MEMBERSHIP, project_id=ProjectId(UUID(int=90))),),
    ],
)
async def test_reader_cannot_widen_scope_or_change_combined_order(
    items: tuple[MyProjectAccessGrantDTO | MyProjectAccessRelationshipDTO, ...],
) -> None:
    with pytest.raises(RuntimeError):
        await MyProjectAccessService(MockOwnAccessFacts(replace(FACTS, items=items))).get_access(
            access=ACCESS, query=GetMyProjectAccessQuery(PROJECT)
        )


@pytest.mark.asyncio
async def test_page_bound_is_checked_before_returning_private_assignments() -> None:
    with pytest.raises(RuntimeError):
        await MyProjectAccessService(MockOwnAccessFacts()).get_access(
            access=ACCESS, query=GetMyProjectAccessQuery(PROJECT, 1)
        )


@pytest.mark.asyncio
async def test_dependency_failure_is_safe_and_cancellation_remains_cancellation() -> None:
    facts = MockOwnAccessFacts()
    facts.error = TimeoutError()
    service = MyProjectAccessService(facts)
    with pytest.raises(DependencyUnavailableError):
        await service.get_access(access=ACCESS, query=GetMyProjectAccessQuery(PROJECT))

    cancelled = asyncio.CancelledError()
    facts.error = cancelled
    with pytest.raises(asyncio.CancelledError) as raised:
        await service.get_access(access=ACCESS, query=GetMyProjectAccessQuery(PROJECT))
    assert raised.value is cancelled
