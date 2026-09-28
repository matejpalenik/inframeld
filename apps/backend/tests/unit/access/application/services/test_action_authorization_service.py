"""Verify current visibility controls disclosure before action admission."""

from dataclasses import replace
from typing import override
from uuid import UUID

import pytest

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
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
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ResourceNotFoundError,
)

ACCESS = AccessContextDTO(PrincipalId(UUID(int=1)))
TARGET = ProjectActionTargetDTO(ProjectId(UUID(int=2)))
ACTION = ActionId("build")
ORGANIZATION_ID = OrganizationId(UUID(int=3))

ALLOWED_FACTS = ProjectActionFactsDTO(
    organization_id=ORGANIZATION_ID,
    principal_status=PrincipalStatus.ACTIVE,
    project_status=ProjectStatus.ACTIVE,
    is_project_member=True,
    has_exact_action_grant=True,
)


class FixedProjectActionFactsReader(ProjectActionFactsReader):
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
    reader = FixedProjectActionFactsReader(ALLOWED_FACTS)

    authorized_organization_id = await ActionAuthorizationService(reader).require_action(
        access=ACCESS, action_id=ACTION, target=TARGET
    )

    assert authorized_organization_id == ORGANIZATION_ID
    assert reader.last_request == (ACCESS, ACTION, TARGET)


@pytest.mark.asyncio
async def test_visible_project_without_grant_is_forbidden() -> None:
    """Return access denied when visibility holds but the exact action grant is absent."""
    reader = FixedProjectActionFactsReader(replace(ALLOWED_FACTS, has_exact_action_grant=False))

    with pytest.raises(AccessDeniedError):
        await ActionAuthorizationService(reader).require_action(
            access=ACCESS, action_id=ACTION, target=TARGET
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "facts",
    [
        None,
        replace(ALLOWED_FACTS, principal_status=PrincipalStatus.SUSPENDED),
        replace(ALLOWED_FACTS, principal_status=PrincipalStatus.RETIRED),
        replace(ALLOWED_FACTS, project_status=ProjectStatus.DELETING),
        replace(ALLOWED_FACTS, is_project_member=False),
    ],
)
async def test_hidden_project_is_not_found_even_with_a_grant(
    facts: ProjectActionFactsDTO | None,
) -> None:
    """Hide missing or ineligible scope before an action grant can disclose it."""
    reader = FixedProjectActionFactsReader(facts)

    with pytest.raises(ResourceNotFoundError):
        await ActionAuthorizationService(reader).require_action(
            access=ACCESS, action_id=ACTION, target=TARGET
        )
