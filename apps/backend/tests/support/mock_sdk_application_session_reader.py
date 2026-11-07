"""Drive the real identity reader with isolated current account and key observations."""

from dataclasses import replace
from typing import override
from uuid import UUID

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
from inframeld_backend.access.application.dtos.current_application_session_dto import (
    CurrentApplicationSessionDTO,
)
from inframeld_backend.access.application.protocols.application_session_reader import (
    ApplicationSessionReader,
)
from inframeld_backend.access.application.services.application_session_service import (
    ApplicationSessionService,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.application_key_adapter import ApplicationKeyAdapter
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.application_key_audience import (
    ApplicationKeyAudience,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.errors.application_errors import (
    AuthenticationRequiredError,
)
from tests.support.application_key_scenarios import current_key_facts
from tests.support.mock_application_authentication_facts_reader import (
    MockApplicationAuthenticationFactsReader,
)

_PRINCIPAL = PrincipalId(UUID("00000000-0000-4000-8000-000000000008"))
_ORGANIZATION = OrganizationId(UUID("00000000-0000-4000-8000-000000000002"))
_PROJECT = ProjectId(UUID("00000000-0000-4000-8000-000000000003"))
_PROFILE = ApplicationKeyVerificationProfileDTO(
    ApplicationKeyAudience("https://api.test"), ApplicationKeyAdapter.HTTP
)


class MockSDKApplicationSessionReader(ApplicationSessionReader):
    """Exercise safe disclosure and currentness without a database or public key lifecycle."""

    @override
    async def read(self, *, access: AccessContextDTO) -> CurrentApplicationSessionDTO:
        evidence = access.authentication_evidence
        if not isinstance(evidence, ApplicationKeyAuthenticationDTO):
            raise AuthenticationRequiredError()
        key = current_key_facts(
            key_id=evidence.key_id,
            principal_id=_PRINCIPAL,
            organization_id=_ORGANIZATION,
            project_id=_PROJECT,
        )
        if evidence.key_id.value == UUID("00000000-0000-4000-8000-000000000007"):
            key = replace(key, revoked_at=key.checked_at)
        facts = ApplicationAuthenticationFactsDTO(
            principal=Principal(
                _PRINCIPAL,
                _ORGANIZATION,
                PrincipalKind.APPLICATION,
                PrincipalStatus.SUSPENDED
                if evidence.key_id.value == UUID("00000000-0000-4000-8000-000000000009")
                else PrincipalStatus.ACTIVE,
            ),
            project_id=_PROJECT,
            project_status=ProjectStatus.ACTIVE,
            is_project_member=True,
            has_coherent_binding=True,
            key_facts=key,
        )
        return await ApplicationSessionService(
            authentication_facts_reader=MockApplicationAuthenticationFactsReader(facts),
            verification_profile=_PROFILE,
        ).read(access=access)
