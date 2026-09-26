"""Decide whether a linked local principal may authenticate as a human."""

from inframeld_backend.access.domain.principal import Principal, PrincipalKind, PrincipalStatus


def may_authenticate_human(principal: Principal) -> bool:
    """Require the linked principal to be both human and currently active."""
    return principal.kind is PrincipalKind.HUMAN and principal.status is PrincipalStatus.ACTIVE
