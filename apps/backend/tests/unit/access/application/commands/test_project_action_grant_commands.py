from typing import cast
from uuid import UUID

import pytest

from inframeld_backend.access.application.commands.remove_project_action_grant_command import (
    RemoveProjectActionGrantCommand,
)
from inframeld_backend.access.application.commands.set_project_action_grant_command import (
    SetProjectActionGrantCommand,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId

PROJECT = ProjectId(UUID(int=1))
RECIPIENT = PrincipalId(UUID(int=2))
ACTION = ActionId("inspect-budget")


@pytest.mark.parametrize("revision", [0, 2**53 - 1])
def test_reviewed_access_revision_keeps_exact_integer_boundaries(revision: int) -> None:
    command = SetProjectActionGrantCommand(PROJECT, RECIPIENT, ACTION, False, revision)
    removal = RemoveProjectActionGrantCommand(PROJECT, RECIPIENT, ACTION, revision)
    assert command.expected_access_revision == removal.expected_access_revision == revision


@pytest.mark.parametrize("revision", [True, False, "1", 1.0, None])
def test_noninteger_review_cannot_enter_either_mutation(revision: object) -> None:
    with pytest.raises(TypeError):
        SetProjectActionGrantCommand(PROJECT, RECIPIENT, ACTION, False, cast(int, revision))
    with pytest.raises(TypeError):
        RemoveProjectActionGrantCommand(PROJECT, RECIPIENT, ACTION, cast(int, revision))


@pytest.mark.parametrize("revision", [-1, 2**53])
def test_review_outside_signed_bigint_is_rejected(revision: int) -> None:
    with pytest.raises(ValueError):
        SetProjectActionGrantCommand(PROJECT, RECIPIENT, ACTION, False, revision)
    with pytest.raises(ValueError):
        RemoveProjectActionGrantCommand(PROJECT, RECIPIENT, ACTION, revision)


@pytest.mark.parametrize("level", [0, 1, "false", None])
def test_grant_level_requires_a_real_boolean(level: object) -> None:
    with pytest.raises(TypeError):
        SetProjectActionGrantCommand(PROJECT, RECIPIENT, ACTION, cast(bool, level), 0)
