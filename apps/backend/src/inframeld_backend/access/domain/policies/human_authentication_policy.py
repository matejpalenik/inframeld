from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus


class HumanAuthenticationPolicy:
    """Admit a verified identity only when its linked principal is an active human."""

    @staticmethod
    def may_authenticate(principal: Principal) -> bool:
        return principal.kind is PrincipalKind.HUMAN and principal.status is PrincipalStatus.ACTIVE
