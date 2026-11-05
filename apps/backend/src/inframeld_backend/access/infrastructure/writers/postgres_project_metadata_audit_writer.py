from typing import override
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.project_metadata_authority_repaired_audit_event_dto import (
    ProjectMetadataAuthorityRepairedAuditEventDTO,
)
from inframeld_backend.access.application.dtos.project_metadata_changed_audit_event_dto import (
    ProjectMetadataChangedAuditEventDTO,
)
from inframeld_backend.access.application.protocols.project_metadata_audit_writer import (
    ProjectMetadataAuditWriter,
)
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow


class PostgresProjectMetadataAuditWriter(ProjectMetadataAuditWriter):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def changed(self, event: ProjectMetadataChangedAuditEventDTO) -> None:
        self._require_transaction()
        self._session.add(
            AccessAuditEventRow(
                id=uuid4(),
                organization_id=event.organization_id.value,
                project_id=event.project_id.value,
                actor_kind="human",
                actor_principal_id=event.actor_id.value,
                event_type="project_metadata_changed",
                target_kind="project",
                target_id=event.project_id.value,
                action=ProjectAction.EDIT_PROJECT_METADATA.value,
                before_values={"metadata_revision": event.before_revision},
                after_values={
                    "metadata_revision": event.after_revision,
                    "name_changed": event.name_changed,
                    "display_name_changed": event.display_name_changed,
                },
                correlation_id=event.operation_id.value,
            )
        )
        await self._session.flush()

    @override
    async def repaired(self, event: ProjectMetadataAuthorityRepairedAuditEventDTO) -> None:
        self._require_transaction()
        self._session.add(
            AccessAuditEventRow(
                id=uuid4(),
                organization_id=event.organization_id.value,
                project_id=event.project_id.value,
                actor_kind="operator",
                actor_reference=event.operator_label,
                affected_principal_id=event.recipient_id.value,
                event_type="project_metadata_authority_repaired",
                target_kind="project",
                target_id=event.project_id.value,
                action=ProjectAction.EDIT_PROJECT_METADATA.value,
                before_values={"access_revision": event.before_revision},
                after_values={"access_revision": event.after_revision, "can_grant": True},
                reason=event.reason,
                correlation_id=event.operation_id.value,
            )
        )
        await self._session.flush()

    def _require_transaction(self) -> None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Metadata audit requires the active caller transaction.")
