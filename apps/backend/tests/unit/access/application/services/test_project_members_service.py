import asyncio
import base64
import json
from dataclasses import replace
from typing import override
from uuid import UUID

import pytest
from tests.support.authentication_evidence import MockAuthenticationEvidence

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.human_oauth_credential_facts_dto import (
    HumanOAuthCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.dtos.project_member_dto import ProjectMemberDTO
from inframeld_backend.access.application.dtos.project_members_page_facts_dto import (
    ProjectMembersPageFactsDTO,
)
from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
)
from inframeld_backend.access.application.protocols.project_members_facts_reader import (
    ProjectMembersFactsReader,
)
from inframeld_backend.access.application.queries.list_project_members_query import (
    ListProjectMembersQuery,
)
from inframeld_backend.access.application.services.project_members_service import (
    ProjectMembersService,
)
from inframeld_backend.access.application.value_objects.project_members_cursor import (
    ProjectMembersCursor,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
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

ORGANIZATION, PROJECT, INSTALLATION = (
    OrganizationId(UUID(int=2)),
    ProjectId(UUID(int=3)),
    InstallationId(UUID(int=11)),
)
ACTOR = Principal(
    PrincipalId(UUID(int=1)), ORGANIZATION, PrincipalKind.HUMAN, PrincipalStatus.ACTIVE
)
ACCESS = AccessContextDTO(ACTOR.id, MockAuthenticationEvidence.browser())
MEMBERS = (
    ProjectMemberDTO(PrincipalId(UUID(int=10)), "Zoë", PrincipalKind.HUMAN),
    ProjectMemberDTO(PrincipalId(UUID(int=20)), "Alias", PrincipalKind.APPLICATION),
    ProjectMemberDTO(PrincipalId(UUID(int=30)), "Alias", PrincipalKind.HUMAN),
)
ACTION = ProjectActionFactsDTO(ACTOR, False, None, ProjectStatus.ACTIVE, True, True)
FACTS = ProjectMembersPageFactsDTO(INSTALLATION, ORGANIZATION, PROJECT, 7, ACTION, MEMBERS)


def _cursor(
    *,
    installation: InstallationId = INSTALLATION,
    organization: OrganizationId = ORGANIZATION,
    project: ProjectId = PROJECT,
    after: int = 20,
) -> str:
    parts = [
        1,
        "project-members",
        "principal-id-asc",
        str(installation.value),
        str(organization.value),
        str(project.value),
        str(UUID(int=after)),
    ]
    return (
        base64.urlsafe_b64encode(json.dumps(parts, separators=(",", ":")).encode())
        .decode()
        .rstrip("=")
    )


class MockMembersFacts(ProjectMembersFactsReader):
    def __init__(self, result: ProjectMembersPageFactsDTO | None = FACTS) -> None:
        self.result = result
        self.calls: list[tuple[AccessContextDTO, ProjectId, PrincipalId | None, int]] = []
        self.error: BaseException | None = None

    @override
    async def read_page(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        after: PrincipalId | None,
        limit: int,
    ) -> ProjectMembersPageFactsDTO | None:
        self.calls.append((access, project_id, after, limit))
        if self.error is not None:
            raise self.error
        return self.result


@pytest.mark.asyncio
async def test_page_uses_one_current_observation_and_uuid_order_not_labels() -> None:
    facts = MockMembersFacts()
    page = await ProjectMembersService(facts).list_members(
        access=ACCESS, query=ListProjectMembersQuery(PROJECT, 2)
    )
    assert page.project_id == PROJECT and page.access_revision == 7
    assert page.items == MEMBERS[:2]
    assert facts.calls == [(ACCESS, PROJECT, None, 2)]
    assert page.next_cursor == _cursor()
    assert page.next_cursor is not None
    assert ProjectMembersCursor.from_token(page.next_cursor).after == MEMBERS[1].principal_id


@pytest.mark.asyncio
async def test_continuation_returns_fresh_revision_without_a_traversal_snapshot() -> None:
    facts = MockMembersFacts(replace(FACTS, access_revision=12, members=MEMBERS[2:]))
    page = await ProjectMembersService(facts).list_members(
        access=ACCESS, query=ListProjectMembersQuery(PROJECT, 2, _cursor())
    )
    assert page.items == MEMBERS[2:] and page.access_revision == 12 and page.next_cursor is None
    assert facts.calls == [(ACCESS, PROJECT, MEMBERS[1].principal_id, 2)]


@pytest.mark.asyncio
async def test_empty_continuation_retains_authoritative_scope_and_revision() -> None:
    facts = MockMembersFacts(replace(FACTS, members=()))
    page = await ProjectMembersService(facts).list_members(
        access=ACCESS, query=ListProjectMembersQuery(PROJECT, cursor=_cursor(after=30))
    )
    assert page.project_id == PROJECT and page.access_revision == 7
    assert page.items == () and page.next_cursor is None and len(facts.calls) == 1


@pytest.mark.asyncio
async def test_scope_header_absence_is_not_an_empty_success() -> None:
    with pytest.raises(ResourceNotFoundError):
        await ProjectMembersService(MockMembersFacts(None)).list_members(
            access=ACCESS, query=ListProjectMembersQuery(PROJECT)
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["project", "actor", "organization", "revision"])
async def test_substituted_observation_cannot_disclose_members(changed: str) -> None:
    result = (
        replace(FACTS, project_id=ProjectId(UUID(int=99)))
        if changed == "project"
        else replace(
            FACTS, action=replace(ACTION, principal=replace(ACTOR, id=PrincipalId(UUID(int=99))))
        )
        if changed == "actor"
        else replace(FACTS, organization_id=OrganizationId(UUID(int=99)))
        if changed == "organization"
        else replace(FACTS, access_revision=-1)
    )
    result = replace(result, action=replace(result.action, has_exact_action_grant=False))
    with pytest.raises(RuntimeError, match="scope|actor|Project"):
        await ProjectMembersService(MockMembersFacts(result)).list_members(
            access=ACCESS, query=ListProjectMembersQuery(PROJECT)
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("recovery", [False, True])
async def test_ineligible_list_caller_is_forbidden_before_hidden_project_check(
    recovery: bool,
) -> None:
    action = replace(
        ACTION,
        principal=replace(
            ACTOR, status=PrincipalStatus.ACTIVE if recovery else PrincipalStatus.SUSPENDED
        ),
        has_pending_recovery=recovery,
        is_project_member=False,
    )
    with pytest.raises(AccessDeniedError):
        await ProjectMembersService(MockMembersFacts(replace(FACTS, action=action))).list_members(
            access=ACCESS, query=ListProjectMembersQuery(PROJECT)
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [PrincipalStatus.SUSPENDED, PrincipalStatus.RETIRED])
async def test_ineligible_human_cannot_read_even_with_stored_use_authority(
    status: PrincipalStatus,
) -> None:
    facts = replace(FACTS, action=replace(ACTION, principal=replace(ACTOR, status=status)))
    with pytest.raises(AccessDeniedError):
        await ProjectMembersService(MockMembersFacts(facts)).list_members(
            access=ACCESS, query=ListProjectMembersQuery(PROJECT)
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["recovery", "grant", "application"])
async def test_current_eligibility_and_fixed_human_use_action_are_required(changed: str) -> None:
    access = ACCESS
    action = (
        replace(ACTION, has_pending_recovery=True)
        if changed == "recovery"
        else replace(ACTION, has_exact_action_grant=False)
    )
    if changed == "application":
        access = replace(
            ACCESS, authentication_evidence=MockAuthenticationEvidence.application_key()
        )
        action = replace(ACTION, principal=replace(ACTOR, kind=PrincipalKind.APPLICATION))
    with pytest.raises(AccessDeniedError):
        await ProjectMembersService(MockMembersFacts(replace(FACTS, action=action))).list_members(
            access=access, query=ListProjectMembersQuery(PROJECT)
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "member,status",
    [
        (False, ProjectStatus.ACTIVE),
        *[(True, value) for value in ProjectStatus if value is not ProjectStatus.ACTIVE],
    ],
)
async def test_hidden_project_is_not_disclosed_as_a_missing_action(
    member: bool, status: ProjectStatus
) -> None:
    facts = replace(FACTS, action=replace(ACTION, is_project_member=member, project_status=status))
    with pytest.raises(ResourceNotFoundError):
        await ProjectMembersService(MockMembersFacts(facts)).list_members(
            access=ACCESS, query=ListProjectMembersQuery(PROJECT)
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "credential",
    [
        HumanOAuthCredentialFactsDTO(False, HumanCredentialVersion(1)),
        HumanOAuthCredentialFactsDTO(True, HumanCredentialVersion(2)),
        HumanOAuthCredentialFactsDTO(True, None),
    ],
)
async def test_stale_oauth_cannot_reuse_a_membership_cursor(
    credential: HumanOAuthCredentialFactsDTO,
) -> None:
    access = replace(ACCESS, authentication_evidence=MockAuthenticationEvidence.human_oauth())
    facts = replace(FACTS, action=replace(ACTION, oauth_credential_facts=credential))
    with pytest.raises(HumanOAuthCredentialRejectedError):
        await ProjectMembersService(MockMembersFacts(facts)).list_members(
            access=access, query=ListProjectMembersQuery(PROJECT, cursor=_cursor())
        )


@pytest.mark.asyncio
async def test_current_oauth_can_read_the_same_stored_relationships() -> None:
    access = replace(ACCESS, authentication_evidence=MockAuthenticationEvidence.human_oauth())
    facts = replace(
        FACTS,
        action=replace(
            ACTION,
            oauth_credential_facts=HumanOAuthCredentialFactsDTO(True, HumanCredentialVersion(1)),
        ),
    )
    page = await ProjectMembersService(MockMembersFacts(facts)).list_members(
        access=access, query=ListProjectMembersQuery(PROJECT)
    )
    assert page.items == MEMBERS


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "token",
    [
        _cursor(installation=InstallationId(UUID(int=99))),
        _cursor(organization=OrganizationId(UUID(int=99))),
        _cursor(project=ProjectId(UUID(int=99))),
    ],
)
async def test_incompatible_scope_cursor_never_becomes_an_empty_page(token: str) -> None:
    facts = MockMembersFacts(replace(FACTS, members=()))
    with pytest.raises(InvalidInputError):
        await ProjectMembersService(facts).list_members(
            access=ACCESS, query=ListProjectMembersQuery(PROJECT, cursor=token)
        )
    assert facts.calls[0][1] == PROJECT


@pytest.mark.asyncio
async def test_current_authority_precedes_disclosure_or_semantic_scope_error() -> None:
    facts = replace(FACTS, action=replace(ACTION, has_exact_action_grant=False))
    with pytest.raises(AccessDeniedError):
        await ProjectMembersService(MockMembersFacts(facts)).list_members(
            access=ACCESS,
            query=ListProjectMembersQuery(PROJECT, cursor=_cursor(project=ProjectId(UUID(int=99)))),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "members",
    [
        (MEMBERS[1], MEMBERS[0]),
        (MEMBERS[0], MEMBERS[0]),
        (*MEMBERS, ProjectMemberDTO(PrincipalId(UUID(int=40)), "Extra", PrincipalKind.HUMAN)),
    ],
)
async def test_incoherent_order_duplicates_or_overfetch_are_not_success(
    members: tuple[ProjectMemberDTO, ...],
) -> None:
    with pytest.raises(RuntimeError, match="order|bound|duplicate"):
        await ProjectMembersService(MockMembersFacts(replace(FACTS, members=members))).list_members(
            access=ACCESS, query=ListProjectMembersQuery(PROJECT, 2)
        )


@pytest.mark.asyncio
async def test_rows_cannot_resume_at_or_before_the_cursor_position() -> None:
    with pytest.raises(RuntimeError, match="position|order"):
        await ProjectMembersService(MockMembersFacts()).list_members(
            access=ACCESS, query=ListProjectMembersQuery(PROJECT, cursor=_cursor())
        )


@pytest.mark.asyncio
async def test_failed_observation_or_cancellation_never_becomes_an_empty_success() -> None:
    facts = MockMembersFacts()
    error = DependencyUnavailableError()
    facts.error = error
    with pytest.raises(DependencyUnavailableError) as raised:
        await ProjectMembersService(facts).list_members(
            access=ACCESS, query=ListProjectMembersQuery(PROJECT)
        )
    assert raised.value is error
    facts.error = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await ProjectMembersService(facts).list_members(
            access=ACCESS, query=ListProjectMembersQuery(PROJECT)
        )


@pytest.mark.asyncio
async def test_database_timeout_preserves_diagnostic_cause_and_fails_closed() -> None:
    facts = MockMembersFacts()
    timeout = TimeoutError()
    facts.error = timeout
    with pytest.raises(DependencyUnavailableError) as raised:
        await ProjectMembersService(facts).list_members(
            access=ACCESS, query=ListProjectMembersQuery(PROJECT)
        )
    assert raised.value.__cause__ is timeout
