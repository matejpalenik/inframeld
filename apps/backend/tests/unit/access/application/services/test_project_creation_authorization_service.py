from dataclasses import replace
from typing import override
from uuid import UUID

import pytest
from tests.support.authentication_evidence import MockAuthenticationEvidence

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.organization_access_facts_dto import (
    OrganizationAccessFactsDTO,
)
from inframeld_backend.access.application.dtos.organization_action_grant_dto import (
    OrganizationActionGrantDTO,
)
from inframeld_backend.access.application.protocols.organization_access_facts_reader import (
    OrganizationAccessFactsReader,
)
from inframeld_backend.access.application.services.project_creation_authorization_service import (
    ProjectCreationAuthorizationService,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ResourceNotFoundError,
)


class MockCreationFacts(OrganizationAccessFactsReader):
    def __init__(self, facts: OrganizationAccessFactsDTO | None) -> None:
        self.facts = facts
        self.locked: list[OrganizationId] = []

    @override
    async def read(self, *, access: AccessContextDTO) -> OrganizationAccessFactsDTO | None:
        raise AssertionError("Creation must read after its Organization coordination.")

    @override
    async def read_for_creation(
        self, *, access: AccessContextDTO, organization_id: OrganizationId
    ) -> OrganizationAccessFactsDTO | None:
        self.locked.append(organization_id)
        return self.facts


@pytest.fixture
def facts() -> OrganizationAccessFactsDTO:
    return OrganizationAccessFactsDTO(
        Principal(
            PrincipalId(UUID(int=1)),
            OrganizationId(UUID(int=2)),
            PrincipalKind.HUMAN,
            PrincipalStatus.ACTIVE,
        ),
        7,
        (OrganizationActionGrantDTO(ActionId("create-projects"), False),),
        False,
        None,
    )


@pytest.mark.asyncio
async def test_current_use_only_create_projects_authority_needs_no_existing_project(
    facts: OrganizationAccessFactsDTO,
) -> None:
    reader = MockCreationFacts(facts)
    result = await ProjectCreationAuthorizationService(reader).require_creation(
        access=AccessContextDTO(facts.principal.id, MockAuthenticationEvidence.browser()),
        organization_id=facts.principal.organization_id,
    )
    assert result.organization_id == facts.principal.organization_id
    assert result.project_id is None and result.access_revision == 7
    assert reader.locked == [facts.principal.organization_id]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "condition", ["missing-grant", "wrong-action", "application", "suspended", "recovery"]
)
async def test_denies_current_ineligibility_and_missing_exact_use_authority(
    facts: OrganizationAccessFactsDTO, condition: str
) -> None:
    principal = Principal(
        facts.principal.id,
        facts.principal.organization_id,
        PrincipalKind.APPLICATION if condition == "application" else PrincipalKind.HUMAN,
        PrincipalStatus.SUSPENDED if condition == "suspended" else PrincipalStatus.ACTIVE,
    )
    grants = (
        ()
        if condition == "missing-grant"
        else (OrganizationActionGrantDTO(ActionId("admit-users"), True),)
        if condition == "wrong-action"
        else facts.grants
    )
    changed = replace(
        facts, principal=principal, grants=grants, has_pending_recovery=condition == "recovery"
    )
    evidence = (
        MockAuthenticationEvidence.application_key()
        if condition == "application"
        else MockAuthenticationEvidence.browser()
    )
    with pytest.raises(AccessDeniedError):
        await ProjectCreationAuthorizationService(MockCreationFacts(changed)).require_creation(
            access=AccessContextDTO(principal.id, evidence),
            organization_id=principal.organization_id,
        )


@pytest.mark.asyncio
async def test_scope_is_matched_before_returning_any_authorization(
    facts: OrganizationAccessFactsDTO,
) -> None:
    access = AccessContextDTO(facts.principal.id, MockAuthenticationEvidence.browser())
    with pytest.raises(ResourceNotFoundError):
        await ProjectCreationAuthorizationService(MockCreationFacts(facts)).require_creation(
            access=access, organization_id=OrganizationId(UUID(int=9))
        )
    with pytest.raises(ResourceNotFoundError):
        await ProjectCreationAuthorizationService(MockCreationFacts(None)).require_creation(
            access=access, organization_id=facts.principal.organization_id
        )
    with pytest.raises(RuntimeError):
        await ProjectCreationAuthorizationService(MockCreationFacts(facts)).require_creation(
            access=replace(access, actor_principal_id=PrincipalId(UUID(int=9))),
            organization_id=facts.principal.organization_id,
        )
