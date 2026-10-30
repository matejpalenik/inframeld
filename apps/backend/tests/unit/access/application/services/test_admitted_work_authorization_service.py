from dataclasses import replace
from typing import override
from uuid import UUID

import pytest
from tests.support.authentication_evidence import MockAuthenticationEvidence

from inframeld_backend.access.application.dtos.admitted_work_authority_dto import (
    AdmittedWorkAuthorityDTO,
)
from inframeld_backend.access.application.dtos.admitted_work_facts_dto import AdmittedWorkFactsDTO
from inframeld_backend.access.application.dtos.human_oauth_credential_facts_dto import (
    HumanOAuthCredentialFactsDTO,
)
from inframeld_backend.access.application.protocols.admitted_work_facts_reader import (
    AdmittedWorkFactsReader,
)
from inframeld_backend.access.application.services.admitted_work_authorization_service import (
    AdmittedWorkAuthorizationService,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.errors.application_errors import AccessDeniedError
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

ACTOR = Principal(
    PrincipalId(UUID(int=1)),
    OrganizationId(UUID(int=2)),
    PrincipalKind.APPLICATION,
    PrincipalStatus.ACTIVE,
)
AUTHORITY = AdmittedWorkAuthorityDTO(
    ACTOR.id,
    ACTOR.kind,
    InstallationId(UUID(int=3)),
    ACTOR.organization_id,
    ProjectId(UUID(int=4)),
    ActionId("query"),
    None,
)
FACTS = AdmittedWorkFactsDTO(
    ACTOR, AUTHORITY.installation_id, ProjectStatus.ACTIVE, True, True, False, None
)


class MockAdmittedWorkFactsReader(AdmittedWorkFactsReader):
    def __init__(self, facts: AdmittedWorkFactsDTO | None) -> None:
        self.facts = facts

    @override
    async def read(self, authority: AdmittedWorkAuthorityDTO) -> AdmittedWorkFactsDTO | None:
        return self.facts


@pytest.mark.asyncio
async def test_admitted_application_uses_current_account_authority_without_origin_key() -> None:
    await AdmittedWorkAuthorizationService(MockAdmittedWorkFactsReader(FACTS)).require_current(
        AUTHORITY
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "facts",
    [
        None,
        replace(FACTS, has_exact_action_grant=False),
        replace(FACTS, is_project_member=False),
        replace(FACTS, has_pending_recovery=True),
        replace(FACTS, project_status=ProjectStatus.DELETING),
        replace(
            FACTS,
            principal=Principal(
                ACTOR.id, ACTOR.organization_id, ACTOR.kind, PrincipalStatus.SUSPENDED
            ),
        ),
    ],
)
async def test_lost_current_authority_stops_later_protected_work(
    facts: AdmittedWorkFactsDTO | None,
) -> None:
    with pytest.raises(AccessDeniedError):
        await AdmittedWorkAuthorizationService(MockAdmittedWorkFactsReader(facts)).require_current(
            AUTHORITY
        )


@pytest.mark.asyncio
async def test_changed_human_recovery_generation_stops_original_work() -> None:
    binding = MockAuthenticationEvidence.human_oauth()
    human = Principal(ACTOR.id, ACTOR.organization_id, PrincipalKind.HUMAN, PrincipalStatus.ACTIVE)
    authority = replace(AUTHORITY, principal_kind=PrincipalKind.HUMAN, human_binding=binding)
    facts = replace(
        FACTS,
        principal=human,
        human_generation=HumanOAuthCredentialFactsDTO(
            True, HumanCredentialVersion(binding.version.value + 1)
        ),
    )

    with pytest.raises(AccessDeniedError):
        await AdmittedWorkAuthorizationService(MockAdmittedWorkFactsReader(facts)).require_current(
            authority
        )
