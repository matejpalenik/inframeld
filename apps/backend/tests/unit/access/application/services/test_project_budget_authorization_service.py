"""Check budget authority using supplied authentication evidence and current facts.

Application-key evidence is simulated here. These decisions do not qualify an
incoming key authenticator, provider verification or transactional write locks.
"""

from dataclasses import replace
from typing import override
from uuid import UUID

import pytest
from tests.support.authentication_evidence import MockAuthenticationEvidence

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.human_oauth_credential_facts_dto import (
    HumanOAuthCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.project_action_authorization_dto import (
    ProjectActionAuthorizationDTO,
)
from inframeld_backend.access.application.dtos.project_action_authorization_request_dto import (
    ProjectActionAuthorizationRequestDTO,
)
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.dtos.project_action_target_dto import (
    ProjectActionTargetDTO,
)
from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
)
from inframeld_backend.access.application.protocols.project_action_facts_reader import (
    ProjectActionFactsReader,
)
from inframeld_backend.access.application.services.project_budget_authorization_service import (
    ProjectBudgetAuthorizationService,
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
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ResourceNotFoundError,
)

ACTOR_ID = PrincipalId(UUID(int=1))
PROJECT_ID = ProjectId(UUID(int=2))
ORGANIZATION_ID = OrganizationId(UUID(int=3))
HUMAN = Principal(ACTOR_ID, ORGANIZATION_ID, PrincipalKind.HUMAN, PrincipalStatus.ACTIVE)
HUMAN_ACCESS = AccessContextDTO(ACTOR_ID, MockAuthenticationEvidence.browser())
CURRENT_FACTS = ProjectActionFactsDTO(
    principal=HUMAN,
    has_pending_recovery=False,
    oauth_credential_facts=None,
    project_status=ProjectStatus.ACTIVE,
    is_project_member=True,
    has_exact_action_grant=True,
)


class MockProjectActionFactsReader(ProjectActionFactsReader):
    """Supply one current observation without verifying credentials or taking locks."""

    def __init__(self, facts: ProjectActionFactsDTO | None) -> None:
        self.facts = facts
        self.last_request: tuple[AccessContextDTO, ActionId, ProjectActionTargetDTO] | None = None

    @override
    async def read_action_facts(
        self, *, access: AccessContextDTO, action_id: ActionId, target: ProjectActionTargetDTO
    ) -> ProjectActionFactsDTO | None:
        self.last_request = (access, action_id, target)
        return self.facts


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["inspect-budget", "manage-budget"])
async def test_authorizes_current_human_for_the_exact_budget_action(action: str) -> None:
    reader = MockProjectActionFactsReader(CURRENT_FACTS)
    request = ProjectActionAuthorizationRequestDTO(PROJECT_ID, ActionId(action))

    result = await ProjectBudgetAuthorizationService(reader).require_authorization(
        access=HUMAN_ACCESS, request=request
    )

    assert result == ProjectActionAuthorizationDTO(ORGANIZATION_ID, PROJECT_ID)
    assert reader.last_request == (
        HUMAN_ACCESS,
        request.action_id,
        ProjectActionTargetDTO(PROJECT_ID),
    )


@pytest.mark.asyncio
async def test_application_can_inspect_with_its_own_exact_grant() -> None:
    access = AccessContextDTO(ACTOR_ID, MockAuthenticationEvidence.application_key())
    reader = MockProjectActionFactsReader(
        replace(CURRENT_FACTS, principal=replace(HUMAN, kind=PrincipalKind.APPLICATION))
    )

    result = await ProjectBudgetAuthorizationService(reader).require_authorization(
        access=access,
        request=ProjectActionAuthorizationRequestDTO(PROJECT_ID, ActionId("inspect-budget")),
    )

    assert result == ProjectActionAuthorizationDTO(ORGANIZATION_ID, PROJECT_ID)


@pytest.mark.asyncio
async def test_application_cannot_manage_even_with_a_stored_management_grant() -> None:
    access = AccessContextDTO(ACTOR_ID, MockAuthenticationEvidence.application_key())
    reader = MockProjectActionFactsReader(
        replace(CURRENT_FACTS, principal=replace(HUMAN, kind=PrincipalKind.APPLICATION))
    )

    with pytest.raises(AccessDeniedError):
        await ProjectBudgetAuthorizationService(reader).require_authorization(
            access=access,
            request=ProjectActionAuthorizationRequestDTO(PROJECT_ID, ActionId("manage-budget")),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["inspect-budget", "manage-budget"])
async def test_project_membership_does_not_supply_a_missing_budget_grant(action: str) -> None:
    reader = MockProjectActionFactsReader(replace(CURRENT_FACTS, has_exact_action_grant=False))

    with pytest.raises(AccessDeniedError):
        await ProjectBudgetAuthorizationService(reader).require_authorization(
            access=HUMAN_ACCESS,
            request=ProjectActionAuthorizationRequestDTO(PROJECT_ID, ActionId(action)),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "facts",
    [
        None,
        replace(CURRENT_FACTS, is_project_member=False),
        replace(CURRENT_FACTS, project_status=ProjectStatus.DELETING),
        replace(CURRENT_FACTS, principal=replace(HUMAN, status=PrincipalStatus.SUSPENDED)),
        replace(CURRENT_FACTS, principal=replace(HUMAN, status=PrincipalStatus.RETIRED)),
    ],
)
async def test_hidden_scope_does_not_disclose_budget_authority(
    facts: ProjectActionFactsDTO | None,
) -> None:
    reader = MockProjectActionFactsReader(facts)

    with pytest.raises(ResourceNotFoundError):
        await ProjectBudgetAuthorizationService(reader).require_authorization(
            access=HUMAN_ACCESS,
            request=ProjectActionAuthorizationRequestDTO(PROJECT_ID, ActionId("inspect-budget")),
        )


@pytest.mark.asyncio
async def test_recovery_blocks_management_on_an_otherwise_visible_project() -> None:
    reader = MockProjectActionFactsReader(replace(CURRENT_FACTS, has_pending_recovery=True))

    with pytest.raises(AccessDeniedError):
        await ProjectBudgetAuthorizationService(reader).require_authorization(
            access=HUMAN_ACCESS,
            request=ProjectActionAuthorizationRequestDTO(PROJECT_ID, ActionId("manage-budget")),
        )


@pytest.mark.asyncio
async def test_stale_oauth_evidence_is_rejected_before_hidden_scope_disclosure() -> None:
    evidence = MockAuthenticationEvidence.human_oauth()
    access = AccessContextDTO(ACTOR_ID, evidence)
    reader = MockProjectActionFactsReader(
        replace(
            CURRENT_FACTS,
            is_project_member=False,
            oauth_credential_facts=HumanOAuthCredentialFactsDTO(
                binding_matches_actor=True, current_version=HumanCredentialVersion(2)
            ),
        )
    )

    with pytest.raises(HumanOAuthCredentialRejectedError):
        await ProjectBudgetAuthorizationService(reader).require_authorization(
            access=access,
            request=ProjectActionAuthorizationRequestDTO(PROJECT_ID, ActionId("manage-budget")),
        )


@pytest.mark.asyncio
async def test_current_oauth_evidence_can_manage_with_current_authority() -> None:
    evidence = MockAuthenticationEvidence.human_oauth()
    access = AccessContextDTO(ACTOR_ID, evidence)
    reader = MockProjectActionFactsReader(
        replace(
            CURRENT_FACTS,
            oauth_credential_facts=HumanOAuthCredentialFactsDTO(
                binding_matches_actor=True, current_version=evidence.version
            ),
        )
    )

    result = await ProjectBudgetAuthorizationService(reader).require_authorization(
        access=access,
        request=ProjectActionAuthorizationRequestDTO(PROJECT_ID, ActionId("manage-budget")),
    )

    assert result == ProjectActionAuthorizationDTO(ORGANIZATION_ID, PROJECT_ID)


@pytest.mark.asyncio
async def test_an_unrelated_action_cannot_use_the_budget_capability() -> None:
    reader = MockProjectActionFactsReader(CURRENT_FACTS)

    with pytest.raises(AccessDeniedError):
        await ProjectBudgetAuthorizationService(reader).require_authorization(
            access=HUMAN_ACCESS,
            request=ProjectActionAuthorizationRequestDTO(PROJECT_ID, ActionId("delete-project")),
        )


@pytest.mark.asyncio
async def test_fact_identity_cannot_replace_the_authenticated_actor() -> None:
    reader = MockProjectActionFactsReader(
        replace(CURRENT_FACTS, principal=replace(HUMAN, id=PrincipalId(UUID(int=99))))
    )

    with pytest.raises(RuntimeError, match="authenticated actor"):
        await ProjectBudgetAuthorizationService(reader).require_authorization(
            access=HUMAN_ACCESS,
            request=ProjectActionAuthorizationRequestDTO(PROJECT_ID, ActionId("manage-budget")),
        )
