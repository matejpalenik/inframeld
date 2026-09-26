"""Verify current visibility controls disclosure before action admission."""

from dataclasses import replace
from typing import override
from uuid import UUID

import pytest

from inframeld_backend.access.application.access_context import AccessContext
from inframeld_backend.access.application.authorization.action_authorization_service import (
    ActionAuthorizationService,
)
from inframeld_backend.access.application.authorization.action_facts_reader import ActionFactsReader
from inframeld_backend.access.application.authorization.current_action_facts import (
    CurrentActionFacts,
)
from inframeld_backend.access.application.authorization.project_action_target import (
    ProjectActionTarget,
)
from inframeld_backend.access.domain.action_values import ActionId
from inframeld_backend.access.domain.principal import PrincipalId, PrincipalStatus
from inframeld_backend.access.domain.project_values import ProjectId, ProjectStatus
from inframeld_backend.shared.application.errors import AccessDeniedError, ResourceNotFoundError

ACCESS = AccessContext(PrincipalId(UUID(int=1)))
TARGET = ProjectActionTarget(ProjectId(UUID(int=2)))
ACTION = ActionId("build")

ALLOWED_FACTS = CurrentActionFacts(
    principal_status=PrincipalStatus.ACTIVE,
    project_status=ProjectStatus.ACTIVE,
    is_project_member=True,
    has_exact_action_grant=True,
)


class FixedActionFactsReader(ActionFactsReader):
    """Return chosen stored facts and record the exact requested scope."""

    def __init__(self, facts: CurrentActionFacts | None) -> None:
        """Choose the state observed by this authorization attempt."""
        self._facts = facts
        self.last_request: tuple[AccessContext, ActionId, ProjectActionTarget] | None = None

    @override
    async def read_action_facts(
        self, *, access: AccessContext, action: ActionId, target: ProjectActionTarget
    ) -> CurrentActionFacts | None:
        """Record the lookup and return its configured state without I/O."""
        self.last_request = (access, action, target)
        return self._facts


@pytest.mark.asyncio
async def test_allows_current_member_with_exact_grant() -> None:
    """Admit eligible callers using facts for the exact actor, action, and project."""
    reader = FixedActionFactsReader(ALLOWED_FACTS)

    await ActionAuthorizationService(reader).require_action(
        access=ACCESS, action=ACTION, target=TARGET
    )

    assert reader.last_request == (ACCESS, ACTION, TARGET)


@pytest.mark.asyncio
async def test_visible_project_without_grant_is_forbidden() -> None:
    """Return access denied when visibility holds but the exact action grant is absent."""
    reader = FixedActionFactsReader(replace(ALLOWED_FACTS, has_exact_action_grant=False))

    with pytest.raises(AccessDeniedError):
        await ActionAuthorizationService(reader).require_action(
            access=ACCESS, action=ACTION, target=TARGET
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
    facts: CurrentActionFacts | None,
) -> None:
    """Hide missing or ineligible scope before an action grant can disclose it."""
    reader = FixedActionFactsReader(facts)

    with pytest.raises(ResourceNotFoundError):
        await ActionAuthorizationService(reader).require_action(
            access=ACCESS, action=ACTION, target=TARGET
        )
