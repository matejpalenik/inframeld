from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.policies.principal_access_policy import PrincipalAccessPolicy
from inframeld_backend.access.domain.policy_inputs.principal_access_policy_input import (
    PrincipalAccessPolicyInput,
)
from inframeld_backend.access.domain.value_objects.access_group_relationships import (
    AccessGroupRelationships,
)


class AccessGroupRelationshipPolicy:
    """Decide recipient eligibility and keep management inside ordinary membership."""

    @staticmethod
    def may_add_member(
        *,
        principal: Principal,
        is_project_member: bool,
        has_coherent_identity: bool,
        has_pending_recovery: bool,
    ) -> bool:
        """Check a target account for new membership without authenticating it.

        Human targets require a coherent admitted identity, not a presented credential.
        """
        return (
            is_project_member
            and (principal.kind is not PrincipalKind.HUMAN or has_coherent_identity)
            and PrincipalAccessPolicy.may_use_product(
                PrincipalAccessPolicyInput(
                    principal=principal,
                    has_pending_recovery=has_pending_recovery,
                    credential_is_current=True,
                )
            )
        )

    @staticmethod
    def supports_manager_kind(principal_kind: PrincipalKind) -> bool:
        return principal_kind is PrincipalKind.HUMAN

    @staticmethod
    def add_member(before: AccessGroupRelationships) -> AccessGroupRelationships:
        return AccessGroupRelationships(member=True, manager=before.manager)

    @staticmethod
    def remove_member(before: AccessGroupRelationships) -> AccessGroupRelationships:
        return AccessGroupRelationships(member=False, manager=False)

    @staticmethod
    def appoint_manager(before: AccessGroupRelationships) -> AccessGroupRelationships:
        return AccessGroupRelationships(member=True, manager=True)

    @staticmethod
    def remove_manager(before: AccessGroupRelationships) -> AccessGroupRelationships:
        return AccessGroupRelationships(member=before.member, manager=False)
