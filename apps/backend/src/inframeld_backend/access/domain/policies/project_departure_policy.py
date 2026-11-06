from inframeld_backend.access.domain.enums.access_group_action import AccessGroupAction
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_departure_target_kind import (
    ProjectDepartureTargetKind,
)
from inframeld_backend.access.domain.policies.principal_access_policy import PrincipalAccessPolicy
from inframeld_backend.access.domain.policies.project_action_eligibility_policy import (
    ProjectActionEligibilityPolicy,
)
from inframeld_backend.access.domain.policy_inputs.principal_access_policy_input import (
    PrincipalAccessPolicyInput,
)
from inframeld_backend.access.domain.policy_inputs.project_departure_responsibility_policy_input import (
    ProjectDepartureResponsibilityPolicyInput,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId

_GROUP_DOCUMENT_ACTIONS = frozenset(AccessGroupAction)


class ProjectDeparturePolicy:
    """Protect the remaining human authority for an ordinary Project departure."""

    @staticmethod
    def supports_responsibility(*, target_kind: str, action_id: ActionId | None) -> bool:
        """Reject unusable stored assignments instead of treating them as a grantor."""
        if action_id is None:
            return target_kind == ProjectDepartureTargetKind.ACCESS_GROUP
        if target_kind == ProjectDepartureTargetKind.PROJECT:
            return ProjectActionEligibilityPolicy.may_use(
                action_id=action_id, principal_kind=PrincipalKind.HUMAN
            )
        if target_kind == ProjectDepartureTargetKind.ACCESS_GROUP:
            return action_id.value in _GROUP_DOCUMENT_ACTIONS
        if target_kind == ProjectDepartureTargetKind.APPLICATION_ACCOUNT:
            return action_id.value in {
                "issue-application-keys",
                "revoke-application-keys",
                "delete-application-account",
            }
        return False

    @staticmethod
    def may_depart(
        responsibilities: tuple[ProjectDepartureResponsibilityPolicyInput, ...],
    ) -> bool:
        for responsibility in responsibilities:
            if not ProjectDeparturePolicy.supports_responsibility(
                target_kind=responsibility.target_kind, action_id=responsibility.action_id
            ):
                return False

            requires_group_manager = responsibility.action_id is None
            allows_group_manager = (
                responsibility.target_kind == ProjectDepartureTargetKind.ACCESS_GROUP
                and responsibility.action_id is not None
                and responsibility.action_id.value in _GROUP_DOCUMENT_ACTIONS
            )
            supported = False
            for candidate in responsibility.candidates:
                if (
                    candidate.principal.kind is not PrincipalKind.HUMAN
                    or not candidate.is_project_member
                    or not candidate.has_coherent_identity
                    or not PrincipalAccessPolicy.may_use_product(
                        PrincipalAccessPolicyInput(
                            principal=candidate.principal,
                            has_pending_recovery=candidate.has_pending_recovery,
                            credential_is_current=True,
                        )
                    )
                ):
                    continue

                manager = candidate.is_group_member and candidate.is_group_manager
                if requires_group_manager:
                    supported = manager
                else:
                    supported = candidate.can_grant or (allows_group_manager and manager)
                if supported:
                    break

            if not supported:
                return False
        return True
