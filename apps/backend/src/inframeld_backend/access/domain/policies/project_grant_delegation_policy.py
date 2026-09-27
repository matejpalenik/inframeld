from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus


class ProjectGrantDelegationPolicy:
    """Decide whether a supported project action may be shared.

    The caller must obtain membership and ``can_grant`` for the same project
    and exact action inside the Access change transaction.
    """

    @staticmethod
    def may_delegate_project_action(
        *,
        actor: Principal,
        actor_is_project_member: bool,
        actor_can_grant_action: bool,
    ) -> bool:
        """Check the grantor without revealing anything about the recipient."""
        return (
            actor.kind is PrincipalKind.HUMAN
            and actor.status is PrincipalStatus.ACTIVE
            and actor_is_project_member
            and actor_can_grant_action
        )

    @staticmethod
    def may_assign_use_only_to_human(
        *,
        actor: Principal,
        recipient: Principal,
        actor_is_project_member: bool,
        recipient_is_project_member: bool,
        actor_can_grant_action: bool,
    ) -> bool:
        return (
            ProjectGrantDelegationPolicy.may_delegate_project_action(
                actor=actor,
                actor_is_project_member=actor_is_project_member,
                actor_can_grant_action=actor_can_grant_action,
            )
            and recipient.kind is PrincipalKind.HUMAN
            and recipient.status is PrincipalStatus.ACTIVE
            and actor.organization_id == recipient.organization_id
            and recipient_is_project_member
        )
