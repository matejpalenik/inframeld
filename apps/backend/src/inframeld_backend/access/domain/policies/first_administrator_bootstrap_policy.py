from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.organization_action import OrganizationAction
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus


class FirstAdministratorBootstrapPolicy:
    ORGANIZATION_NAME = "Inframeld"
    ORGANIZATION_ACTIONS = (
        OrganizationAction.ADMIT_USERS.value,
        OrganizationAction.SUSPEND_USERS.value,
        OrganizationAction.RESTORE_USERS.value,
        OrganizationAction.CREATE_PROJECTS.value,
    )

    @staticmethod
    def may_admit(*, principal: Principal | None, has_pending_recovery: bool) -> bool:
        return not has_pending_recovery and (
            principal is None
            or (
                principal.kind is PrincipalKind.HUMAN and principal.status is PrincipalStatus.ACTIVE
            )
        )
