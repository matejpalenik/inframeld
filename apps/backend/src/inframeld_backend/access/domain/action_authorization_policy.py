"""Decide action admission from current facts without persistence or transport dependencies."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ActionAuthorizationFacts:
    """Describe the current account, project membership, and exact action grant needed for admission."""

    principal_is_active: bool
    is_project_member: bool
    has_exact_action_grant: bool


def may_perform_action(facts: ActionAuthorizationFacts) -> bool:
    """Decide whether these current facts allow the requested action"""
    return facts.principal_is_active and facts.is_project_member and facts.has_exact_action_grant
