from dataclasses import replace
from typing import override
from uuid import uuid4

import pytest
from tests.support.authentication_evidence import MockAuthenticationEvidence

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.dtos.project_metadata_authorization_facts_dto import (
    ProjectMetadataAuthorizationFactsDTO,
)
from inframeld_backend.access.application.protocols.project_metadata_facts_reader import (
    ProjectMetadataFactsReader,
)
from inframeld_backend.access.application.services.project_metadata_authorization_service import (
    ProjectMetadataAuthorizationService,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.resource_name_scope_dto import ResourceNameScopeDTO
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


class MockMetadataFacts(ProjectMetadataFactsReader):
    def __init__(self, kind: PrincipalKind = PrincipalKind.HUMAN, *, granted: bool = True) -> None:
        actor = Principal(
            PrincipalId(uuid4()), OrganizationId(uuid4()), kind, PrincipalStatus.ACTIVE
        )
        self.access = AccessContextDTO(
            actor.id,
            MockAuthenticationEvidence.browser()
            if kind is PrincipalKind.HUMAN
            else MockAuthenticationEvidence.application_key(),
        )
        self.facts = ProjectMetadataAuthorizationFactsDTO(
            ProjectId(uuid4()),
            InstallationId(uuid4()),
            ProjectActionFactsDTO(
                principal=actor,
                has_pending_recovery=False,
                oauth_credential_facts=None,
                project_status=ProjectStatus.ACTIVE,
                is_project_member=True,
                has_exact_action_grant=granted,
            ),
        )

    @override
    async def read(
        self, *, access: AccessContextDTO, project_id: ProjectId
    ) -> ProjectMetadataAuthorizationFactsDTO | None:
        return self.facts

    @override
    async def read_for_change(
        self, *, access: AccessContextDTO, project_id: ProjectId
    ) -> ProjectMetadataAuthorizationFactsDTO | None:
        return self.facts

    @override
    async def scope(self, *, access: AccessContextDTO) -> ResourceNameScopeDTO:
        return ResourceNameScopeDTO(
            self.facts.installation_id, self.facts.action.principal.organization_id
        )


@pytest.mark.asyncio
async def test_member_without_action_can_read_but_cannot_change() -> None:
    facts = MockMetadataFacts(granted=False)
    service = ProjectMetadataAuthorizationService(facts)
    assert (
        await service.require_read(access=facts.access, project_id=facts.facts.project_id)
    ).project_id == facts.facts.project_id
    with pytest.raises(AccessDeniedError):
        await service.require_change(access=facts.access, project_id=facts.facts.project_id)


@pytest.mark.asyncio
async def test_human_metadata_action_is_usable_but_application_stored_grant_is_not() -> None:
    human = MockMetadataFacts()
    assert (
        await ProjectMetadataAuthorizationService(human).require_change(
            access=human.access, project_id=human.facts.project_id
        )
    ).organization_id == human.facts.action.principal.organization_id
    bot = MockMetadataFacts(PrincipalKind.APPLICATION)
    with pytest.raises(AccessDeniedError):
        await ProjectMetadataAuthorizationService(bot).require_change(
            access=bot.access, project_id=bot.facts.project_id
        )


@pytest.mark.asyncio
async def test_lost_membership_hides_metadata_and_recovery_blocks_change() -> None:
    facts = MockMetadataFacts()
    facts.facts = replace(facts.facts, action=replace(facts.facts.action, is_project_member=False))
    with pytest.raises(ResourceNotFoundError):
        await ProjectMetadataAuthorizationService(facts).require_read(
            access=facts.access, project_id=facts.facts.project_id
        )
    facts.facts = replace(
        facts.facts,
        action=replace(facts.facts.action, is_project_member=True, has_pending_recovery=True),
    )
    with pytest.raises(AccessDeniedError):
        await ProjectMetadataAuthorizationService(facts).require_change(
            access=facts.access, project_id=facts.facts.project_id
        )
