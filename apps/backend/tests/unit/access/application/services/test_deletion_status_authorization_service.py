"""Require fresh human eligibility without borrowing ordinary Project read authority."""

from dataclasses import replace
from typing import override
from uuid import UUID

import pytest
from tests.support.authentication_evidence import MockAuthenticationEvidence

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.deletion_status_authorization_dto import (
    DeletionStatusAuthorizationDTO,
)
from inframeld_backend.access.application.dtos.deletion_status_authorization_request_dto import (
    DeletionStatusAuthorizationRequestDTO,
)
from inframeld_backend.access.application.dtos.deletion_status_facts_dto import (
    DeletionStatusFactsDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_facts_dto import (
    HumanOAuthCredentialFactsDTO,
)
from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
)
from inframeld_backend.access.application.protocols.deletion_status_facts_reader import (
    DeletionStatusFactsReader,
)
from inframeld_backend.access.application.services.deletion_status_authorization_service import (
    DeletionStatusAuthorizationService,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

ACTOR = Principal(
    PrincipalId(UUID(int=1)),
    OrganizationId(UUID(int=2)),
    PrincipalKind.HUMAN,
    PrincipalStatus.ACTIVE,
)
ACCESS = AccessContextDTO(ACTOR.id, MockAuthenticationEvidence.browser())
REQUEST = DeletionStatusAuthorizationRequestDTO(OperationId("original-deletion"))
FACTS = DeletionStatusFactsDTO(InstallationId(UUID(int=3)), ACTOR, False, None)


class MockDeletionFacts(DeletionStatusFactsReader):
    def __init__(self, result: DeletionStatusFactsDTO | None = FACTS) -> None:
        self.result = result
        self.failure: Exception | None = None
        self.calls: list[AccessContextDTO] = []

    @override
    async def read(self, *, access: AccessContextDTO) -> DeletionStatusFactsDTO | None:
        self.calls.append(access)
        if self.failure is not None:
            raise self.failure
        return self.result


@pytest.mark.asyncio
async def test_eligible_human_needs_no_project_membership_or_delete_grant_facts() -> None:
    reader = MockDeletionFacts()
    result = await DeletionStatusAuthorizationService(reader).require_authorization(
        access=ACCESS, request=REQUEST
    )
    assert result == DeletionStatusAuthorizationDTO(
        REQUEST.operation_id, FACTS.installation_id, ACTOR.organization_id, ACTOR.id
    )
    assert reader.calls == [ACCESS]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "facts",
    [
        None,
        replace(FACTS, has_pending_recovery=True),
        replace(FACTS, principal=replace(ACTOR, status=PrincipalStatus.SUSPENDED)),
        replace(FACTS, principal=replace(ACTOR, status=PrincipalStatus.RETIRED)),
        replace(FACTS, principal=replace(ACTOR, kind=PrincipalKind.APPLICATION)),
    ],
)
async def test_current_ineligible_actor_is_denied(facts: DeletionStatusFactsDTO | None) -> None:
    with pytest.raises(AccessDeniedError):
        await DeletionStatusAuthorizationService(MockDeletionFacts(facts)).require_authorization(
            access=ACCESS, request=REQUEST
        )


@pytest.mark.asyncio
async def test_application_evidence_cannot_claim_the_human_exception() -> None:
    access = replace(ACCESS, authentication_evidence=MockAuthenticationEvidence.application_key())
    with pytest.raises(AccessDeniedError):
        await DeletionStatusAuthorizationService(MockDeletionFacts()).require_authorization(
            access=access, request=REQUEST
        )


@pytest.mark.asyncio
async def test_facts_for_another_principal_are_a_contract_failure() -> None:
    facts = replace(FACTS, principal=replace(ACTOR, id=PrincipalId(UUID(int=99))))
    with pytest.raises(RuntimeError, match="different principal"):
        await DeletionStatusAuthorizationService(MockDeletionFacts(facts)).require_authorization(
            access=ACCESS, request=REQUEST
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "oauth_facts",
    [
        HumanOAuthCredentialFactsDTO(False, HumanCredentialVersion(1)),
        HumanOAuthCredentialFactsDTO(True, None),
        HumanOAuthCredentialFactsDTO(True, HumanCredentialVersion(2)),
    ],
)
async def test_stale_or_mismatched_oauth_is_rejected_before_product_eligibility(
    oauth_facts: HumanOAuthCredentialFactsDTO,
) -> None:
    access = replace(ACCESS, authentication_evidence=MockAuthenticationEvidence.human_oauth())
    facts = replace(FACTS, has_pending_recovery=True, oauth_credential_facts=oauth_facts)
    with pytest.raises(HumanOAuthCredentialRejectedError):
        await DeletionStatusAuthorizationService(MockDeletionFacts(facts)).require_authorization(
            access=access, request=REQUEST
        )


@pytest.mark.asyncio
async def test_current_oauth_uses_the_same_original_principal_scope() -> None:
    access = replace(ACCESS, authentication_evidence=MockAuthenticationEvidence.human_oauth())
    facts = replace(
        FACTS, oauth_credential_facts=HumanOAuthCredentialFactsDTO(True, HumanCredentialVersion(1))
    )
    result = await DeletionStatusAuthorizationService(
        MockDeletionFacts(facts)
    ).require_authorization(access=access, request=REQUEST)
    assert result.principal_id == ACTOR.id
    assert result.operation_id == REQUEST.operation_id


@pytest.mark.asyncio
async def test_missing_oauth_facts_are_not_treated_as_current() -> None:
    access = replace(ACCESS, authentication_evidence=MockAuthenticationEvidence.human_oauth())
    with pytest.raises(RuntimeError, match="OAuth evidence"):
        await DeletionStatusAuthorizationService(MockDeletionFacts()).require_authorization(
            access=access, request=REQUEST
        )


@pytest.mark.asyncio
async def test_prior_success_does_not_cache_current_eligibility() -> None:
    reader = MockDeletionFacts()
    service = DeletionStatusAuthorizationService(reader)
    await service.require_authorization(access=ACCESS, request=REQUEST)
    reader.result = replace(FACTS, has_pending_recovery=True)
    with pytest.raises(AccessDeniedError):
        await service.require_authorization(access=ACCESS, request=REQUEST)
    assert reader.calls == [ACCESS, ACCESS]


@pytest.mark.asyncio
async def test_unavailable_current_facts_are_not_missing_history() -> None:
    reader = MockDeletionFacts()
    reader.failure = DependencyUnavailableError()
    with pytest.raises(DependencyUnavailableError):
        await DeletionStatusAuthorizationService(reader).require_authorization(
            access=ACCESS, request=REQUEST
        )
