"""Bound group visibility and each membership page to current exact relationships."""

from dataclasses import replace
from typing import override
from uuid import UUID

import pytest
from tests.support.application_key_scenarios import current_key_facts
from tests.support.authentication_evidence import MockAuthenticationEvidence
from tests.support.mock_project_metadata import (
    ACCESS,
    ORGANIZATION_ID,
    PROJECT_ID,
    SAVED_RESULT,
    MockTransactions,
)

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.access_group_metadata_dto import (
    AccessGroupMetadataDTO,
)
from inframeld_backend.access.application.dtos.access_group_principal_dto import (
    AccessGroupPrincipalDTO,
)
from inframeld_backend.access.application.dtos.access_group_read_facts_dto import (
    AccessGroupReadFactsDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_facts_dto import (
    HumanOAuthCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.enums.access_group_collection import AccessGroupCollection
from inframeld_backend.access.application.errors.application_key_credential_rejected_error import (
    ApplicationKeyCredentialRejectedError,
)
from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
)
from inframeld_backend.access.application.protocols.access_group_read_facts_reader import (
    AccessGroupReadFactsReader,
)
from inframeld_backend.access.application.queries.list_access_group_principals_query import (
    ListAccessGroupPrincipalsQuery,
)
from inframeld_backend.access.application.services.access_group_read_service import (
    AccessGroupReadService,
)
from inframeld_backend.access.application.value_objects.access_group_principals_cursor import (
    AccessGroupPrincipalsCursor,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    InvalidInputError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName

GROUP = AccessGroupId(UUID(int=10))
META = AccessGroupMetadataDTO(
    organization_id=ORGANIZATION_ID,
    project_id=PROJECT_ID,
    group_id=GROUP,
    name=ResourceName("support"),
    display_name="Support",
    created_at=SAVED_RESULT.expires_at,
    access_revision=7,
)
ACTION = ProjectActionFactsDTO(
    principal=Principal(
        ACCESS.actor_principal_id, ORGANIZATION_ID, PrincipalKind.HUMAN, PrincipalStatus.ACTIVE
    ),
    has_pending_recovery=False,
    oauth_credential_facts=None,
    project_status=ProjectStatus.ACTIVE,
    is_project_member=True,
    has_exact_action_grant=False,
)
FACTS = AccessGroupReadFactsDTO(
    installation_id=InstallationId(UUID(int=20)),
    group=META,
    action=ACTION,
    is_member=True,
    is_manager=True,
    has_group_action=False,
)
ITEMS = tuple(
    AccessGroupPrincipalDTO(PrincipalId(UUID(int=i)), PrincipalKind.HUMAN, f"Human {i}")
    for i in (30, 31, 32)
)


class MockReadFacts(AccessGroupReadFactsReader):
    def __init__(self) -> None:
        self.facts: AccessGroupReadFactsDTO | None = FACTS
        self.page_calls = 0
        self.after: PrincipalId | None = None

    @override
    async def read(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        selector: AccessGroupId | ResourceName,
    ) -> AccessGroupReadFactsDTO | None:
        return self.facts

    @override
    async def principals(
        self,
        *,
        facts: AccessGroupReadFactsDTO,
        collection: AccessGroupCollection,
        after: PrincipalId | None,
        limit: int,
    ) -> tuple[AccessGroupPrincipalDTO, ...]:
        self.page_calls += 1
        self.after = after
        return tuple(
            item for item in ITEMS if after is None or item.principal_id.value > after.value
        )[: limit + 1]


@pytest.mark.asyncio
@pytest.mark.parametrize("relationship", ["member", "manager", "action"])
async def test_exact_relationship_allows_safe_metadata(relationship: str) -> None:
    reader = MockReadFacts()
    reader.facts = replace(
        FACTS,
        is_member=relationship == "member",
        is_manager=relationship == "manager",
        has_group_action=relationship == "action",
    )
    result = await AccessGroupReadService(MockTransactions([]), reader).inspect(
        access=ACCESS, project_id=PROJECT_ID, selector=GROUP
    )
    assert result == META and reader.page_calls == 0


@pytest.mark.asyncio
async def test_eligible_project_outsider_cannot_resolve_group_or_list_people() -> None:
    reader = MockReadFacts()
    reader.facts = replace(FACTS, is_member=False, is_manager=False, has_group_action=False)
    service = AccessGroupReadService(MockTransactions([]), reader)
    with pytest.raises(ResourceNotFoundError):
        await service.inspect(
            access=ACCESS, project_id=PROJECT_ID, selector=ResourceName("support")
        )
    with pytest.raises((ResourceNotFoundError, AccessDeniedError)):
        await service.list_principals(
            access=ACCESS,
            query=ListAccessGroupPrincipalsQuery(PROJECT_ID, GROUP, AccessGroupCollection.MEMBERS),
        )
    assert reader.page_calls == 0


@pytest.mark.asyncio
async def test_page_is_bounded_and_cursor_is_exact_group_and_collection_scoped() -> None:
    reader = MockReadFacts()
    service = AccessGroupReadService(MockTransactions([]), reader)
    first = await service.list_principals(
        access=ACCESS,
        query=ListAccessGroupPrincipalsQuery(PROJECT_ID, GROUP, AccessGroupCollection.MEMBERS, 2),
    )
    assert first.items == ITEMS[:2] and first.next_cursor is not None
    cursor = AccessGroupPrincipalsCursor.from_token(first.next_cursor)
    assert (cursor.group_id, cursor.collection, cursor.after) == (
        GROUP,
        AccessGroupCollection.MEMBERS,
        ITEMS[1].principal_id,
    )
    last = await service.list_principals(
        access=ACCESS,
        query=ListAccessGroupPrincipalsQuery(
            PROJECT_ID, GROUP, AccessGroupCollection.MEMBERS, 2, first.next_cursor
        ),
    )
    assert last.items == ITEMS[2:] and last.next_cursor is None
    with pytest.raises(InvalidInputError):
        await service.list_principals(
            access=ACCESS,
            query=ListAccessGroupPrincipalsQuery(
                PROJECT_ID, GROUP, AccessGroupCollection.MANAGERS, 2, first.next_cursor
            ),
        )
    assert reader.page_calls == 2


@pytest.mark.asyncio
async def test_lost_management_denies_continuation_before_loading_page() -> None:
    reader = MockReadFacts()
    reader.facts = replace(FACTS, is_manager=False)
    with pytest.raises(AccessDeniedError):
        await AccessGroupReadService(MockTransactions([]), reader).list_principals(
            access=ACCESS,
            query=ListAccessGroupPrincipalsQuery(PROJECT_ID, GROUP, AccessGroupCollection.MEMBERS),
        )
    assert reader.page_calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("is_project_member", [False, True])
async def test_stale_oauth_is_rejected_before_project_visibility_or_recovery(
    is_project_member: bool,
) -> None:
    reader = MockReadFacts()
    reader.facts = replace(
        FACTS,
        action=replace(
            ACTION,
            is_project_member=is_project_member,
            has_pending_recovery=True,
            oauth_credential_facts=HumanOAuthCredentialFactsDTO(
                binding_matches_actor=True,
                current_version=HumanCredentialVersion(2),
            ),
        ),
    )
    access = replace(ACCESS, authentication_evidence=MockAuthenticationEvidence.human_oauth())

    with pytest.raises(HumanOAuthCredentialRejectedError):
        await AccessGroupReadService(MockTransactions([]), reader).inspect(
            access=access, project_id=PROJECT_ID, selector=GROUP
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("hidden", ["inactive-principal", "deleting-project", "nonmember"])
async def test_hidden_project_stays_not_found_before_recovery_or_group_relationships(
    hidden: str,
) -> None:
    reader = MockReadFacts()
    reader.facts = replace(
        FACTS,
        action=replace(
            ACTION,
            principal=replace(
                ACTION.principal,
                status=PrincipalStatus.SUSPENDED
                if hidden == "inactive-principal"
                else PrincipalStatus.ACTIVE,
            ),
            project_status=ProjectStatus.DELETING
            if hidden == "deleting-project"
            else ProjectStatus.ACTIVE,
            is_project_member=hidden != "nonmember",
            has_pending_recovery=True,
        ),
    )

    with pytest.raises(ResourceNotFoundError):
        await AccessGroupReadService(MockTransactions([]), reader).inspect(
            access=ACCESS, project_id=PROJECT_ID, selector=GROUP
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("has_group_relationship", [False, True])
async def test_recovery_denies_a_visible_project_before_group_visibility_or_page_inventory(
    has_group_relationship: bool,
) -> None:
    reader = MockReadFacts()
    reader.facts = replace(
        FACTS,
        action=replace(ACTION, has_pending_recovery=True),
        is_member=has_group_relationship,
        is_manager=has_group_relationship,
        has_group_action=False,
    )

    with pytest.raises(AccessDeniedError):
        await AccessGroupReadService(MockTransactions([]), reader).list_principals(
            access=ACCESS,
            query=ListAccessGroupPrincipalsQuery(PROJECT_ID, GROUP, AccessGroupCollection.MEMBERS),
        )
    assert reader.page_calls == 0


@pytest.mark.asyncio
async def test_application_group_metadata_requires_its_current_key_and_exact_relationship() -> None:
    reader = MockReadFacts()
    evidence = MockAuthenticationEvidence.application_key()
    key = current_key_facts(
        key_id=evidence.key_id,
        principal_id=ACTION.principal.id,
        organization_id=ORGANIZATION_ID,
        project_id=PROJECT_ID,
    )
    reader.facts = replace(
        FACTS,
        action=replace(
            ACTION,
            principal=replace(ACTION.principal, kind=PrincipalKind.APPLICATION),
            application_key_facts=key,
        ),
    )
    access = AccessContextDTO(ACTION.principal.id, evidence)
    service = AccessGroupReadService(MockTransactions([]), reader)
    assert await service.inspect(access=access, project_id=PROJECT_ID, selector=GROUP) == META
    with pytest.raises(AccessDeniedError):
        await service.list_principals(
            access=access,
            query=ListAccessGroupPrincipalsQuery(PROJECT_ID, GROUP, AccessGroupCollection.MEMBERS),
        )
    reader.facts = replace(
        reader.facts,
        action=replace(
            reader.facts.action, application_key_facts=replace(key, revoked_at=key.checked_at)
        ),
    )
    with pytest.raises(ApplicationKeyCredentialRejectedError):
        await service.inspect(access=access, project_id=PROJECT_ID, selector=GROUP)
    assert reader.page_calls == 0
