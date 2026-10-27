from inframeld_backend.access.domain.entities.identity_recovery import IdentityRecovery
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.policies.principal_access_policy import PrincipalAccessPolicy


class IdentityRecoveryReleasePolicy:
    """Decide whether this finished checklist may release its own access block."""

    @staticmethod
    def may_release(*, recovery: IdentityRecovery, principal: Principal | None) -> bool:
        return recovery.is_cleanup_confirmed and (
            principal is None
            or (
                principal.kind is PrincipalKind.HUMAN
                and PrincipalAccessPolicy.is_account_active(principal)
            )
        )
