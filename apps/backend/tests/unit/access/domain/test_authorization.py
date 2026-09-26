"""Verify the Access domain's deny-by-default action authorization rule."""

import pytest

from inframeld_backend.access.domain.authorization import (
    ActionAuthorizationFacts,
    may_perform_action,
)


@pytest.mark.parametrize(
    ("facts", "expected"),
    [
        (
            ActionAuthorizationFacts(
                principal_is_active=True,
                is_project_member=True,
                has_exact_action_grant=True,
            ),
            True,
        ),
        (
            ActionAuthorizationFacts(
                principal_is_active=True,
                is_project_member=True,
                has_exact_action_grant=False,
            ),
            False,
        ),
        (
            ActionAuthorizationFacts(
                principal_is_active=True,
                is_project_member=False,
                has_exact_action_grant=True,
            ),
            False,
        ),
        (
            ActionAuthorizationFacts(
                principal_is_active=False,
                is_project_member=True,
                has_exact_action_grant=True,
            ),
            False,
        ),
    ],
)
def test_action_requires_an_active_project_member_with_an_exact_grant(
    facts: ActionAuthorizationFacts, expected: bool
) -> None:
    """Allow an action only when all three required authorization facts are true."""
    assert may_perform_action(facts) is expected
