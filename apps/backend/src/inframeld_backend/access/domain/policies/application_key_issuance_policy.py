from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.policies.principal_access_policy import PrincipalAccessPolicy


class ApplicationKeyIssuancePolicy:
    """Require the complete current account authority, never an issuer ceiling."""

    @staticmethod
    def may_issue_for_account(
        *,
        application_principal: Principal,
        is_project_member: bool,
        has_all_action_delegation: bool,
        manages_all_groups: bool,
    ) -> bool:
        return (
            application_principal.kind is PrincipalKind.APPLICATION
            and PrincipalAccessPolicy.is_account_active(application_principal)
            and is_project_member
            and has_all_action_delegation
            and manages_all_groups
        )
