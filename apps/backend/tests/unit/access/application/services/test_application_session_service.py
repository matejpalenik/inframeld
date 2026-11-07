import asyncio
from dataclasses import replace
from uuid import UUID

import pytest
from tests.support.application_key_scenarios import current_key_facts
from tests.support.authentication_evidence import MockAuthenticationEvidence
from tests.support.mock_application_authentication_facts_reader import (
    MockApplicationAuthenticationFactsReader,
)

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_authentication_facts_dto import (
    ApplicationAuthenticationFactsDTO,
)
from inframeld_backend.access.application.dtos.current_application_session_dto import (
    CurrentApplicationSessionDTO,
)
from inframeld_backend.access.application.errors.application_key_credential_rejected_error import (
    ApplicationKeyCredentialRejectedError,
)
from inframeld_backend.access.application.services.application_session_service import (
    ApplicationSessionService,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    AuthenticationRequiredError,
    DependencyUnavailableError,
)

pytestmark = pytest.mark.asyncio
EVIDENCE = MockAuthenticationEvidence.application_key()
ACTOR = Principal(
    PrincipalId(UUID(int=1)),
    OrganizationId(UUID(int=2)),
    PrincipalKind.APPLICATION,
    PrincipalStatus.ACTIVE,
)
PROJECT = ProjectId(UUID(int=3))
ACCESS = AccessContextDTO(ACTOR.id, EVIDENCE)
KEY_FACTS = current_key_facts(
    key_id=EVIDENCE.key_id,
    principal_id=ACTOR.id,
    organization_id=ACTOR.organization_id,
    project_id=PROJECT,
)
FACTS = ApplicationAuthenticationFactsDTO(
    principal=ACTOR,
    project_id=PROJECT,
    project_status=ProjectStatus.ACTIVE,
    is_project_member=True,
    has_coherent_binding=True,
    key_facts=KEY_FACTS,
)


async def test_session_returns_only_current_actor_and_bound_project() -> None:
    reader = MockApplicationAuthenticationFactsReader(FACTS)
    result = await ApplicationSessionService(
        authentication_facts_reader=reader, verification_profile=KEY_FACTS.expected_profile
    ).read(access=ACCESS)
    assert result == CurrentApplicationSessionDTO(ACTOR.id, PROJECT)
    assert reader.current_profiles == [KEY_FACTS.expected_profile]


async def test_revocation_between_authentication_and_disclosure_is_rejected() -> None:
    reader = MockApplicationAuthenticationFactsReader(
        replace(FACTS, key_facts=replace(KEY_FACTS, revoked_at=KEY_FACTS.checked_at))
    )
    with pytest.raises(ApplicationKeyCredentialRejectedError):
        await ApplicationSessionService(
            authentication_facts_reader=reader, verification_profile=KEY_FACTS.expected_profile
        ).read(access=ACCESS)


async def test_current_local_ineligibility_remains_separate_from_key_rejection() -> None:
    reader = MockApplicationAuthenticationFactsReader(
        replace(FACTS, principal=replace(ACTOR, status=PrincipalStatus.SUSPENDED))
    )
    with pytest.raises(AccessDeniedError):
        await ApplicationSessionService(
            authentication_facts_reader=reader, verification_profile=KEY_FACTS.expected_profile
        ).read(access=ACCESS)


async def test_missing_profile_cannot_disclose_identity() -> None:
    reader = MockApplicationAuthenticationFactsReader(FACTS)
    with pytest.raises(DependencyUnavailableError):
        await ApplicationSessionService(
            authentication_facts_reader=reader, verification_profile=None
        ).read(access=ACCESS)
    assert reader.current_profiles == []


async def test_identity_reader_rejects_a_human_context_before_account_read() -> None:
    reader = MockApplicationAuthenticationFactsReader(FACTS)
    with pytest.raises(AuthenticationRequiredError):
        await ApplicationSessionService(
            authentication_facts_reader=reader, verification_profile=KEY_FACTS.expected_profile
        ).read(access=AccessContextDTO(ACTOR.id, MockAuthenticationEvidence.browser()))
    assert reader.current_profiles == []


async def test_current_read_is_bounded_and_cancellation_propagates() -> None:
    reader = MockApplicationAuthenticationFactsReader(FACTS)
    reader.stall = True
    service = ApplicationSessionService(
        authentication_facts_reader=reader,
        verification_profile=KEY_FACTS.expected_profile,
        total_timeout_seconds=0.01,
    )
    with pytest.raises(DependencyUnavailableError):
        await service.read(access=ACCESS)
    reader.stall = False
    reader.failure = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await service.read(access=ACCESS)


async def test_disappeared_key_is_invalid_before_disclosing_account_binding() -> None:
    missing = replace(KEY_FACTS, principal_id=None, project_id=None, expires_at=None)
    reader = MockApplicationAuthenticationFactsReader(replace(FACTS, key_facts=missing))
    with pytest.raises(ApplicationKeyCredentialRejectedError):
        await ApplicationSessionService(
            authentication_facts_reader=reader, verification_profile=KEY_FACTS.expected_profile
        ).read(access=ACCESS)
