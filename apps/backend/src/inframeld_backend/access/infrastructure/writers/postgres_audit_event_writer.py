from typing import override
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

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
    async def append(self, event: ProjectUseOnlyGrantAssignedAuditEventDTO) -> None:
        self._session.add(
            AccessAuditEventRow(
                id=uuid4(),
                organization_id=event.organization_id.value,
                project_id=event.project_id.value,
                actor_kind=PrincipalKind.HUMAN.value,
                actor_principal_id=event.actor_principal_id.value,
                affected_principal_id=event.recipient_principal_id.value,
                event_type="project_action_grant_assigned",
                target_kind="project",
                target_id=event.project_id.value,
                action=event.action_id.value,
                after_values={"can_grant": False},
                correlation_id=event.operation_id.value,
            )
        )
        await self._session.flush()
