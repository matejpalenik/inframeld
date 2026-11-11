from dataclasses import replace
from typing import override
from uuid import UUID

import pytest
from tests.support.authentication_evidence import MockAuthenticationEvidence

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.human_credential_facts_dto import (
    HumanCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.organization_access_facts_dto import (
    OrganizationAccessFactsDTO,
)
from inframeld_backend.access.application.dtos.organization_action_grant_dto import (
    OrganizationActionGrantDTO,
)
from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
)
from inframeld_backend.access.application.protocols.organization_access_facts_reader import (
    OrganizationAccessFactsReader,
)
from inframeld_backend.access.application.services.my_organization_access_service import (
    MyOrganizationAccessService,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    AuthenticationRequiredError,
    ResourceNotFoundError,
)


class MockOrganizationFacts(OrganizationAccessFactsReader):
    def __init__(self, facts: OrganizationAccessFactsDTO | None) -> None:
        self.facts = facts

    @override
    async def read(self, *, access: AccessContextDTO) -> OrganizationAccessFactsDTO | None:
        return self.facts

    @override
    async def read_for_creation(
        self, *, access: AccessContextDTO, organization_id: OrganizationId
    ) -> OrganizationAccessFactsDTO | None:
        raise AssertionError("Own-access observation must not take a creation lock.")


@pytest.mark.asyncio
async def test_eligible_human_reads_empty_assignments_without_create_projects_permission() -> None:
    principal = Principal(
        PrincipalId(UUID(int=1)),
        OrganizationId(UUID(int=2)),
        PrincipalKind.HUMAN,
        PrincipalStatus.ACTIVE,
    )
    facts = OrganizationAccessFactsDTO(
        principal, 7, (), False, HumanCredentialFactsDTO(True, HumanCredentialVersion(1))
    )
    result = await MyOrganizationAccessService(MockOrganizationFacts(facts)).read(
        access=AccessContextDTO(principal.id, MockAuthenticationEvidence.browser())
    )
    assert result.organization_id == principal.organization_id
    assert result.principal_id == principal.id
    assert result.access_revision == 7
    assert result.grants == ()


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
        (),
        False,
        HumanCredentialFactsDTO(True, HumanCredentialVersion(1)),
    )


@pytest.mark.asyncio
async def test_returns_actual_supported_assignments_without_promoting_use_only(
    facts: OrganizationAccessFactsDTO,
) -> None:
    grants = (
        OrganizationActionGrantDTO(ActionId("admit-users"), False),
        OrganizationActionGrantDTO(ActionId("restore-users"), True),
    )
    result = await MyOrganizationAccessService(
        MockOrganizationFacts(replace(facts, grants=grants))
    ).read(access=AccessContextDTO(facts.principal.id, MockAuthenticationEvidence.browser()))
    assert result.grants == grants
    assert result.access_revision == 7


@pytest.mark.asyncio
@pytest.mark.parametrize("condition", ["application", "suspended", "retired", "recovery"])
async def test_ineligible_actor_cannot_read_own_assignments(
    facts: OrganizationAccessFactsDTO, condition: str
) -> None:
    principal = Principal(
        facts.principal.id,
        facts.principal.organization_id,
        PrincipalKind.APPLICATION if condition == "application" else PrincipalKind.HUMAN,
        PrincipalStatus.SUSPENDED
        if condition == "suspended"
        else PrincipalStatus.RETIRED
        if condition == "retired"
        else PrincipalStatus.ACTIVE,
    )
    changed = replace(facts, principal=principal, has_pending_recovery=condition == "recovery")
    evidence = (
        MockAuthenticationEvidence.application_key()
        if condition == "application"
        else MockAuthenticationEvidence.browser()
    )
    with pytest.raises(AccessDeniedError):
        await MyOrganizationAccessService(MockOrganizationFacts(changed)).read(
            access=AccessContextDTO(principal.id, evidence)
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("current", [None, HumanCredentialVersion(2), HumanCredentialVersion(1)])
async def test_oauth_rechecks_current_generation_and_actor_binding(
    facts: OrganizationAccessFactsDTO, current: HumanCredentialVersion | None
) -> None:
    changed = replace(
        facts,
        oauth_credential_facts=HumanCredentialFactsDTO(
            current != HumanCredentialVersion(1), current
        ),
    )
    with pytest.raises(HumanOAuthCredentialRejectedError):
        await MyOrganizationAccessService(MockOrganizationFacts(changed)).read(
            access=AccessContextDTO(facts.principal.id, MockAuthenticationEvidence.human_oauth())
        )


@pytest.mark.asyncio
async def test_current_oauth_evidence_can_observe_empty_grants(
    facts: OrganizationAccessFactsDTO,
) -> None:
    changed = replace(
        facts, oauth_credential_facts=HumanCredentialFactsDTO(True, HumanCredentialVersion(1))
    )
    result = await MyOrganizationAccessService(MockOrganizationFacts(changed)).read(
        access=AccessContextDTO(facts.principal.id, MockAuthenticationEvidence.human_oauth())
    )
    assert result.grants == ()


@pytest.mark.asyncio
async def test_absent_or_wrong_actor_facts_cannot_disclose_another_organization(
    facts: OrganizationAccessFactsDTO,
) -> None:
    access = AccessContextDTO(PrincipalId(UUID(int=9)), MockAuthenticationEvidence.browser())
    with pytest.raises(ResourceNotFoundError):
        await MyOrganizationAccessService(MockOrganizationFacts(None)).read(access=access)
    with pytest.raises(RuntimeError):
        await MyOrganizationAccessService(MockOrganizationFacts(facts)).read(access=access)


@pytest.mark.asyncio
@pytest.mark.parametrize("oauth", [False, True])
async def test_browser_currentness_preserves_the_presented_credential_family(
    oauth: bool, facts: OrganizationAccessFactsDTO
) -> None:
    """Reject stale evidence before disclosing data, recovering originals or changing authority."""
    evidence = (
        MockAuthenticationEvidence.human_oauth() if oauth else MockAuthenticationEvidence.browser()
    )
    stale = HumanCredentialFactsDTO(True, HumanCredentialVersion(2))
    expected = HumanOAuthCredentialRejectedError if oauth else AuthenticationRequiredError
    observed = replace(facts, oauth_credential_facts=stale)
    with pytest.raises(AuthenticationRequiredError) as caught:
        await MyOrganizationAccessService(MockOrganizationFacts(observed)).read(
            access=AccessContextDTO(facts.principal.id, evidence)
        )
    assert type(caught.value) is expected
