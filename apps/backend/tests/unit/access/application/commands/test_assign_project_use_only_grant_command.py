from typing import cast
from uuid import UUID

import pytest

from inframeld_backend.access.application.commands.assign_project_use_only_grant_command import (
    AssignProjectUseOnlyGrantCommand,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


def _command(revision: int) -> AssignProjectUseOnlyGrantCommand:
    return AssignProjectUseOnlyGrantCommand(
        project_id=ProjectId(UUID(int=1)),
        recipient_principal_id=PrincipalId(UUID(int=2)),
        action_id=ActionId("create-access-groups"),
        expected_access_revision=revision,
    )


@pytest.mark.parametrize("revision", [0, 7])
def test_accepts_nonnegative_revisions(revision: int) -> None:
    assert _command(revision).expected_access_revision == revision


def test_rejects_negative_revision() -> None:
    """Non-HTTP callers must also supply a meaningful expected revision."""
    with pytest.raises(ValueError):
        _command(-1)


@pytest.mark.parametrize("revision", [True, False, "0", 1.5, None])
def test_rejects_values_that_are_not_whole_revisions(revision: object) -> None:
    # Deliberately bypass static checking to exercise runtime input validation.
    with pytest.raises(TypeError):
        _command(cast(int, revision))
