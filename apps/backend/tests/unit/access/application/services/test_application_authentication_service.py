import asyncio
from dataclasses import replace
from typing import override
from uuid import UUID

import pytest

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_authentication_facts_dto import (
    ApplicationAuthenticationFactsDTO,
)
from inframeld_backend.access.application.dtos.application_key_authentication_dto import (
    ApplicationKeyAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.application_key_verification_profile_dto import (
    ApplicationKeyVerificationProfileDTO,
)
from inframeld_backend.access.application.dtos.verified_application_key_dto import (
    VerifiedApplicationKeyDTO,
)
from inframeld_backend.access.application.protocols.application_authentication_facts_reader import (
    ApplicationAuthenticationFactsReader,
)
from inframeld_backend.access.application.protocols.application_key_verifier import (
    ApplicationKeyVerifier,
)
from inframeld_backend.access.application.services.application_authentication_service import (
    ApplicationAuthenticationService,
)
from inframeld_backend.access.application.value_objects.application_key_credential import (
    ApplicationKeyCredential,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.application_key_adapter import ApplicationKeyAdapter
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.application_key_audience import (
    ApplicationKeyAudience,
)
from inframeld_backend.access.domain.value_objects.application_key_id import ApplicationKeyId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    AuthenticationRequiredError,
    DependencyUnavailableError,
)

pytestmark = pytest.mark.asyncio
PRINCIPAL = Principal(
    PrincipalId(UUID(int=1)),
    OrganizationId(UUID(int=2)),
    PrincipalKind.APPLICATION,
    PrincipalStatus.ACTIVE,
)
KEY_ID = ApplicationKeyId(UUID(int=3))
PROJECT = ProjectId(UUID(int=4))
PROFILE = ApplicationKeyVerificationProfileDTO(
    ApplicationKeyAudience("https://api.test"), ApplicationKeyAdapter.HTTP
)
CREDENTIAL = ApplicationKeyCredential(f"ifm_app_{KEY_ID.value}_" + "A" * 43)
FACTS = ApplicationAuthenticationFactsDTO(
    principal=PRINCIPAL,
    project_id=PROJECT,
    project_status=ProjectStatus.ACTIVE,
    is_project_member=True,
    has_coherent_binding=True,
)


class MockVerifier(ApplicationKeyVerifier):
    def __init__(self) -> None:
        self.result: VerifiedApplicationKeyDTO | None = VerifiedApplicationKeyDTO(
            KEY_ID, PRINCIPAL.id
        )
        self.failure: BaseException | None = None
        self.profile: ApplicationKeyVerificationProfileDTO | None = None

    @override
    async def verify(
        self, credential: ApplicationKeyCredential, *, profile: ApplicationKeyVerificationProfileDTO
    ) -> VerifiedApplicationKeyDTO | None:
        self.profile = profile
        if self.failure is not None:
            raise self.failure
        return self.result


class MockFactsReader(ApplicationAuthenticationFactsReader):
    def __init__(self) -> None:
        self.result: ApplicationAuthenticationFactsDTO | None = FACTS
        self.principal_ids: list[PrincipalId] = []

    @override
    async def read(self, principal_id: PrincipalId) -> ApplicationAuthenticationFactsDTO | None:
        self.principal_ids.append(principal_id)
        return self.result

    @override
    async def read_current(
        self, *, access: AccessContextDTO, profile: ApplicationKeyVerificationProfileDTO
    ) -> ApplicationAuthenticationFactsDTO | None:
        raise AssertionError("Authentication must load current account separately from disclosure.")


def service(
    verifier: MockVerifier,
    reader: MockFactsReader,
    *,
    profile: ApplicationKeyVerificationProfileDTO | None = PROFILE,
) -> ApplicationAuthenticationService:
    return ApplicationAuthenticationService(
        key_verifier=verifier, authentication_facts_reader=reader, verification_profile=profile
    )


async def test_verified_key_is_separately_admitted_as_its_own_application() -> None:
    verifier, reader = MockVerifier(), MockFactsReader()
    access = await service(verifier, reader).authenticate(CREDENTIAL)
    assert access == AccessContextDTO(PRINCIPAL.id, ApplicationKeyAuthenticationDTO(KEY_ID))
    assert reader.principal_ids == [PRINCIPAL.id]
    assert verifier.profile == PROFILE
    assert CREDENTIAL.value not in repr(access)


async def test_key_rejection_precedes_account_read() -> None:
    verifier, reader = MockVerifier(), MockFactsReader()
    verifier.result = None
    with pytest.raises(AuthenticationRequiredError):
        await service(verifier, reader).authenticate(CREDENTIAL)
    assert reader.principal_ids == []


@pytest.mark.parametrize(
    "facts",
    [
        None,
        replace(FACTS, is_project_member=False),
        replace(FACTS, has_coherent_binding=False),
        replace(FACTS, project_status=ProjectStatus.DELETING),
        replace(FACTS, principal=replace(PRINCIPAL, status=PrincipalStatus.SUSPENDED)),
        replace(FACTS, principal=replace(PRINCIPAL, kind=PrincipalKind.HUMAN)),
    ],
)
async def test_verified_but_locally_ineligible_account_is_denied(
    facts: ApplicationAuthenticationFactsDTO | None,
) -> None:
    verifier, reader = MockVerifier(), MockFactsReader()
    reader.result = facts
    with pytest.raises(AccessDeniedError):
        await service(verifier, reader).authenticate(CREDENTIAL)


@pytest.mark.parametrize(
    "failure", [DependencyUnavailableError(), RuntimeError("unexpected"), asyncio.CancelledError()]
)
async def test_verification_failures_propagate_without_account_read(failure: BaseException) -> None:
    verifier, reader = MockVerifier(), MockFactsReader()
    verifier.failure = failure
    with pytest.raises(type(failure)):
        await service(verifier, reader).authenticate(CREDENTIAL)
    assert reader.principal_ids == []


async def test_missing_profile_is_unavailable_without_verification() -> None:
    verifier, reader = MockVerifier(), MockFactsReader()
    with pytest.raises(DependencyUnavailableError):
        await service(verifier, reader, profile=None).authenticate(CREDENTIAL)
    assert verifier.profile is None
    assert reader.principal_ids == []


async def test_account_reader_cannot_substitute_another_actor() -> None:
    verifier, reader = MockVerifier(), MockFactsReader()
    reader.result = replace(FACTS, principal=replace(PRINCIPAL, id=PrincipalId(UUID(int=99))))
    with pytest.raises(RuntimeError):
        await service(verifier, reader).authenticate(CREDENTIAL)
