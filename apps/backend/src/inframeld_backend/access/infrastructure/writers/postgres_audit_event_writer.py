from typing import override
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.access_action_grant_changed_audit_event_dto import (
    AccessActionGrantChangedAuditEventDTO,
)
from inframeld_backend.access.application.dtos.access_group_grant_target_dto import (
    AccessGroupGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.organization_grant_target_dto import (
    OrganizationGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.project_action_grant_changed_audit_event_dto import (
    ProjectActionGrantChangedAuditEventDTO,
)
from inframeld_backend.access.application.dtos.project_use_only_grant_assigned_audit_event_dto import (
    ProjectUseOnlyGrantAssignedAuditEventDTO,
)
from inframeld_backend.access.application.protocols.audit_event_writer import AuditEventWriter
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow


class PostgresAuditEventWriter(AuditEventWriter):
    """Map human grant assignments to audit rows and flush the shared session.

    Store the original operation ID as the audit correlation ID.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def append(
        self,
        event: (
            ProjectUseOnlyGrantAssignedAuditEventDTO
            | ProjectActionGrantChangedAuditEventDTO
            | AccessActionGrantChangedAuditEventDTO
        ),
    ) -> None:
        if isinstance(event, AccessActionGrantChangedAuditEventDTO):
            target = event.target
            if isinstance(target, OrganizationGrantTargetDTO):
                if target.organization_id != event.organization_id:
                    raise RuntimeError("Grant audit changed its Organization target.")
                project_id = None
                target_id = target.organization_id.value
                target_kind = "organization"
                prefix = "organization_action_grant"
            elif isinstance(target, AccessGroupGrantTargetDTO):
                project_id = target.project_id.value
                target_id = target.access_group_id.value
                target_kind = "access_group"
                prefix = "group_action_grant"
            else:
                project_id = target.project_id.value
                target_id = target.application_principal_id.value
                target_kind = "application_account"
                prefix = "application_action_grant"
        else:
            project_id = event.project_id.value
            target_id = event.project_id.value
            target_kind = "project"
            prefix = "project_action_grant"

        before: dict[str, object] | None = None
        after: dict[str, object] | None = {"can_grant": False}
        event_type = f"{prefix}_assigned"
        if isinstance(
            event, (ProjectActionGrantChangedAuditEventDTO, AccessActionGrantChangedAuditEventDTO)
        ):
            before = (
                {"can_grant": event.before_can_grant}
                if event.before_can_grant is not None
                else None
            )
            after = {"can_grant": event.can_grant} if event.can_grant is not None else None
            event_type = (
                f"{prefix}_removed"
                if event.can_grant is None
                else f"{prefix}_level_changed"
                if event.before_can_grant is not None
                else f"{prefix}_assigned"
            )
        self._session.add(
            AccessAuditEventRow(
                id=uuid4(),
                organization_id=event.organization_id.value,
                project_id=project_id,
                actor_kind=PrincipalKind.HUMAN.value,
                actor_principal_id=event.actor_principal_id.value,
                affected_principal_id=event.recipient_principal_id.value,
                event_type=event_type,
                target_kind=target_kind,
                target_id=target_id,
                action=event.action_id.value,
                before_values=before,
                after_values=after,
                correlation_id=event.operation_id.value,
            )
        )
        await self._session.flush()
