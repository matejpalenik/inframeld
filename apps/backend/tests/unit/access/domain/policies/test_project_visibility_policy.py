"""Verify when authorization may reveal that a project exists."""

import pytest

from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.policies.project_visibility_policy import (
    ProjectVisibilityPolicy,
)


@pytest.mark.parametrize(
    ("principal_status", "project_status", "is_member", "expected"),
    [
        (PrincipalStatus.ACTIVE, ProjectStatus.ACTIVE, True, True),
        (PrincipalStatus.SUSPENDED, ProjectStatus.ACTIVE, True, False),
        (PrincipalStatus.RETIRED, ProjectStatus.ACTIVE, True, False),
        (PrincipalStatus.ACTIVE, ProjectStatus.DELETING, True, False),
        (PrincipalStatus.ACTIVE, ProjectStatus.ACTIVE, False, False),
    ],
)
def test_project_visibility_requires_current_eligibility(
    principal_status: PrincipalStatus,
    project_status: ProjectStatus,
    is_member: bool,
    expected: bool,
) -> None:
    """Expose an active project only to an active principal who currently belongs to it."""
    assert (
        ProjectVisibilityPolicy.may_view_project(
            principal_status=principal_status,
            project_status=project_status,
            is_project_member=is_member,
        )
        is expected
    )
