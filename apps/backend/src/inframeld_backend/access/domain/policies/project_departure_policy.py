from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
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


class ProjectDeparturePolicy:
    """Protect the remaining human authority for an ordinary Project departure."""

    @staticmethod
    def supports_responsibility(
        *, target_kind: str, action_id: ActionId | None, requires_group_manager: bool
    ) -> bool:
        """Reject unusable stored assignments instead of treating them as a grantor."""
        if requires_group_manager:
            return target_kind == "access_group" and action_id is None
        if action_id is None:
            return False
        if target_kind == "project":
            return ProjectActionEligibilityPolicy.may_use(
                action_id=action_id, principal_kind=PrincipalKind.HUMAN
            )
        if target_kind == "access_group":
            return action_id.value in {"add-documents", "update-documents", "delete-documents"}
        if target_kind == "application_account":
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
            supported = False
            for candidate in responsibility.candidates:
                if (
                    candidate.principal.kind is not PrincipalKind.HUMAN
                    or not candidate.is_project_member
                    or not candidate.has_coherent_identity
                    or not PrincipalAccessPolicy.may_use_product(
                        PrincipalAccessPolicyInput(
                            candidate.principal, candidate.has_pending_recovery, True
                        )
                    )
                ):
                    continue

                manager = candidate.is_group_member and candidate.is_group_manager
                if responsibility.requires_group_manager:
                    supported = manager
                else:
                    supported = candidate.can_grant or (
                        responsibility.allows_group_manager and manager
                    )
                if supported:
                    break

            if not supported:
                return False
        return True
