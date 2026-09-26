"""Verify the Access domain's deny-by-default action authorization rule."""

import pytest

from inframeld_backend.access.domain.policies.action_authorization_policy import (
    ActionAuthorizationPolicy,
)
from inframeld_backend.access.domain.policy_inputs.action_authorization_policy_input import (
    ActionAuthorizationPolicyInput,
)


@pytest.mark.parametrize(
    ("facts", "expected"),
    [
        (
            ActionAuthorizationPolicyInput(
                principal_is_active=True,
                is_project_member=True,
                has_exact_action_grant=True,
            ),
            True,
        ),
        (
            ActionAuthorizationPolicyInput(
                principal_is_active=True,
                is_project_member=True,
                has_exact_action_grant=False,
            ),
            False,
        ),
        (
            ActionAuthorizationPolicyInput(
                principal_is_active=True,
                is_project_member=False,
                has_exact_action_grant=True,
            ),
            False,
        ),
        (
            ActionAuthorizationPolicyInput(
                principal_is_active=False,
                is_project_member=True,
                has_exact_action_grant=True,
            ),
            False,
        ),
    ],
)
def test_action_requires_an_active_project_member_with_an_exact_grant(
    facts: ActionAuthorizationPolicyInput, expected: bool
) -> None:
    """Allow an action only when all three required authorization facts are true."""
    assert ActionAuthorizationPolicy.may_perform_action(facts) is expected
