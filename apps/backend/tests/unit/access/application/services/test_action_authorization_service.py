"""Verify current visibility controls disclosure before action admission."""

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
from inframeld_backend.access.application.protocols.project_action_facts_reader import (
    ProjectActionFactsReader,
)
from inframeld_backend.access.application.services.action_authorization_service import (
    ActionAuthorizationService,
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

ACCESS = AccessContextDTO(
    PrincipalId(UUID(int=1)), authentication_evidence=MockAuthenticationEvidence.browser()
)
TARGET = ProjectActionTargetDTO(ProjectId(UUID(int=2)))
ACTION = ActionId("build")
ORGANIZATION_ID = OrganizationId(UUID(int=3))

PRINCIPAL = Principal(
    id=ACCESS.actor_principal_id,
    organization_id=ORGANIZATION_ID,
    kind=PrincipalKind.HUMAN,
    status=PrincipalStatus.ACTIVE,
)

ALLOWED_FACTS = ProjectActionFactsDTO(
    principal=PRINCIPAL,
    has_pending_recovery=False,
    oauth_credential_facts=None,
    project_status=ProjectStatus.ACTIVE,
    is_project_member=True,
    has_exact_action_grant=True,
)


class MockProjectActionFactsReader(ProjectActionFactsReader):
    """Return chosen stored facts and record the exact requested scope."""

    def __init__(self, facts: ProjectActionFactsDTO | None) -> None:
        """Choose the state observed by this authorization attempt."""
        self._facts = facts
        self.last_request: tuple[AccessContextDTO, ActionId, ProjectActionTargetDTO] | None = None

    @override
    async def read_action_facts(
        self, *, access: AccessContextDTO, action_id: ActionId, target: ProjectActionTargetDTO
    ) -> ProjectActionFactsDTO | None:
        """Record the lookup and return its configured state without I/O."""
        self.last_request = (access, action_id, target)
        return self._facts


@pytest.mark.asyncio
async def test_allows_current_member_with_exact_grant() -> None:
    """Admit eligible callers using facts for the exact actor, action, and project."""
    reader = MockProjectActionFactsReader(ALLOWED_FACTS)

    authorization = await ActionAuthorizationService(reader).require_authorization(
        access=ACCESS,
        request=ProjectActionAuthorizationRequestDTO(
            project_id=TARGET.project_id, action_id=ACTION
        ),
    )

    assert authorization == ProjectActionAuthorizationDTO(ORGANIZATION_ID, TARGET.project_id)
    assert reader.last_request == (ACCESS, ACTION, TARGET)


@pytest.mark.asyncio
async def test_visible_project_without_grant_is_forbidden() -> None:
    """Return access denied when visibility holds but the exact action grant is absent."""
    reader = MockProjectActionFactsReader(replace(ALLOWED_FACTS, has_exact_action_grant=False))

    with pytest.raises(AccessDeniedError):
        await ActionAuthorizationService(reader).require_authorization(
            access=ACCESS,
            request=ProjectActionAuthorizationRequestDTO(
                project_id=TARGET.project_id, action_id=ACTION
            ),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "facts",
    [
        None,
        replace(
            ALLOWED_FACTS,
            principal=replace(PRINCIPAL, status=PrincipalStatus.SUSPENDED),
        ),
        replace(
            ALLOWED_FACTS,
            principal=replace(PRINCIPAL, status=PrincipalStatus.RETIRED),
        ),
        replace(ALLOWED_FACTS, project_status=ProjectStatus.DELETING),
        replace(ALLOWED_FACTS, is_project_member=False),
    ],
)
async def test_hidden_project_is_not_found_even_with_a_grant(
    facts: ProjectActionFactsDTO | None,
) -> None:
    """Hide missing or ineligible scope before a grant can disclose the project."""
    reader = MockProjectActionFactsReader(facts)

    with pytest.raises(ResourceNotFoundError):
        await ActionAuthorizationService(reader).require_authorization(
            access=ACCESS,
            request=ProjectActionAuthorizationRequestDTO(
                project_id=TARGET.project_id, action_id=ACTION
            ),
        )


@pytest.mark.asyncio
async def test_recovery_blocks_an_action_on_a_visible_project() -> None:
    """Recovery denies an otherwise authorized member with a forbidden response."""
    facts = replace(
        ALLOWED_FACTS,
        has_pending_recovery=True,
    )
    reader = MockProjectActionFactsReader(facts)

    with pytest.raises(AccessDeniedError):
        await ActionAuthorizationService(reader).require_authorization(
            access=ACCESS,
            request=ProjectActionAuthorizationRequestDTO(
                project_id=TARGET.project_id, action_id=ACTION
            ),
        )


@pytest.mark.asyncio
async def test_recovery_does_not_disclose_a_hidden_project() -> None:
    """A recovery block must not change a nonmember's not-found response."""
    facts = replace(
        ALLOWED_FACTS,
        has_pending_recovery=True,
        is_project_member=False,
    )
    reader = MockProjectActionFactsReader(facts)

    with pytest.raises(ResourceNotFoundError):
        await ActionAuthorizationService(reader).require_authorization(
            access=ACCESS,
            request=ProjectActionAuthorizationRequestDTO(
                project_id=TARGET.project_id, action_id=ACTION
            ),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("visible", [False, True])
@pytest.mark.parametrize("binding_matches_actor, version", [(False, 1), (True, 2), (True, None)])
async def test_stale_credentials_are_rejected_before_authority_can_be_reused(
    visible: bool, binding_matches_actor: bool, version: int | None
) -> None:
    from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
        HumanOAuthCredentialRejectedError,
    )

    stale = replace(
        ALLOWED_FACTS,
        is_project_member=visible,
        oauth_credential_facts=HumanOAuthCredentialFactsDTO(
            binding_matches_actor=binding_matches_actor,
            current_version=HumanCredentialVersion(version) if version is not None else None,
        ),
    )
    with pytest.raises(HumanOAuthCredentialRejectedError):
        await ActionAuthorizationService(MockProjectActionFactsReader(stale)).require_authorization(
            access=replace(
                ACCESS, authentication_evidence=MockAuthenticationEvidence.human_oauth()
            ),
            request=ProjectActionAuthorizationRequestDTO(
                project_id=TARGET.project_id, action_id=ACTION
            ),
        )
