from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus


class HumanAuthenticationPolicy:
    """Require an active human and no unreleased recovery obligation."""

    @staticmethod
    def may_authenticate(principal: Principal, *, has_pending_recovery: bool) -> bool:
        return (
            principal.kind is PrincipalKind.HUMAN
            and principal.status is PrincipalStatus.ACTIVE
            and not has_pending_recovery
        )
