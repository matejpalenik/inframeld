"""Check action authorization outcomes and the facts sent to the Access reader."""

from typing import final
from uuid import UUID

import pytest

from inframeld_backend.access.application.access_authorizer import (
    AccessAuthorizer,
    AccessContext,
    ActionFactsReader,
    ActionTarget,
    CurrentActionFacts,
)
from inframeld_backend.access.domain.authorization import ActionAuthorizationFacts
from inframeld_backend.shared.application.errors import AccessDeniedError, ResourceNotFoundError

PRINCIPAL_ID = UUID("00000000-0000-0000-0000-000000000001")
PROJECT_ID = UUID("00000000-0000-0000-0000-000000000002")
PIPELINE_ID = UUID("00000000-0000-0000-0000-000000000003")

ACCESS = AccessContext(actor_principal_id=PRINCIPAL_ID)
TARGET = ActionTarget(
    project_id=PROJECT_ID,
    target_kind="pipeline",
    target_id=PIPELINE_ID,
)
ACTION = "build"


@final
class MockActionFactsReader(ActionFactsReader):
    """Return fixed authorization facts and record the query made by the authorizer."""

    def __init__(self, facts: CurrentActionFacts) -> None:
        self._facts = facts
        self.last_request: tuple[AccessContext, str, ActionTarget] | None = None

    async def read_action_facts(
        self, *, access: AccessContext, action: str, target: ActionTarget
    ) -> CurrentActionFacts:
        """Record the requested scope and return this test's configured facts."""
        self.last_request = (access, action, target)
        return self._facts


@pytest.mark.asyncio
async def test_allows_visible_target_when_action_facts_allow_action() -> None:
    """Allow the action and pass the caller, action, and target to the reader."""
    reader = MockActionFactsReader(
        CurrentActionFacts(
            authorization=ActionAuthorizationFacts(
                principal_is_active=True,
                is_project_member=True,
                has_exact_action_grant=True,
            ),
            target_is_visible=True,
        )
    )

    authorizer = AccessAuthorizer(reader)

    await authorizer.require_action(access=ACCESS, action=ACTION, target=TARGET)

    assert reader.last_request == (ACCESS, ACTION, TARGET)


@pytest.mark.asyncio
async def test_denies_visible_target_without_exact_action_grant() -> None:
    """Deny a visible target when the caller lacks its exact action grant."""
    reader = MockActionFactsReader(
        CurrentActionFacts(
            authorization=ActionAuthorizationFacts(
                principal_is_active=True, is_project_member=True, has_exact_action_grant=False
            ),
            target_is_visible=True,
        )
    )

    authorizer = AccessAuthorizer(reader)

    with pytest.raises(AccessDeniedError):
        await authorizer.require_action(access=ACCESS, action=ACTION, target=TARGET)


@pytest.mark.asyncio
async def test_hides_target_when_caller_cannot_see_it() -> None:
    """Report a hidden target as not found so its existence is not disclosed."""
    reader = MockActionFactsReader(
        CurrentActionFacts(
            authorization=ActionAuthorizationFacts(
                principal_is_active=True, is_project_member=True, has_exact_action_grant=False
            ),
            target_is_visible=False,
        )
    )

    authorizer = AccessAuthorizer(reader)

    with pytest.raises(ResourceNotFoundError):
        await authorizer.require_action(access=ACCESS, action=ACTION, target=TARGET)
