from typing import override
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.access_group_grant_target_dto import (
    AccessGroupGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.group_manager_repair_responsibility_dto import (
    GroupManagerRepairResponsibilityDTO,
)
from inframeld_backend.access.application.dtos.model_connection_grant_target_dto import (
    ModelConnectionGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.organization_grant_target_dto import (
    OrganizationGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.project_grant_target_dto import ProjectGrantTargetDTO
from inframeld_backend.access.application.dtos.project_metadata_authority_repaired_audit_event_dto import (
    ProjectMetadataAuthorityRepairedAuditEventDTO,
)
from inframeld_backend.access.application.dtos.stranded_authority_repaired_audit_event_dto import (
    StrandedAuthorityRepairedAuditEventDTO,
)
from inframeld_backend.access.application.protocols.project_metadata_audit_writer import (
    ProjectMetadataAuditWriter,
)
from inframeld_backend.access.application.protocols.stranded_authority_audit_writer import (
    StrandedAuthorityAuditWriter,
)
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class PostgresStrandedAuthorityAuditWriter(StrandedAuthorityAuditWriter):
    def __init__(
        self, session: AsyncSession, metadata_audit_writer: ProjectMetadataAuditWriter
    ) -> None:
        self._session = session
        self._metadata_audit_writer = metadata_audit_writer

    @override
    async def repaired(self, event: StrandedAuthorityRepairedAuditEventDTO) -> None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Repair audit requires the active caller transaction.")
        RevisionValidation.require(event.before_revision)
        RevisionValidation.require(event.after_revision)
        if event.after_revision != event.before_revision + 1:
            raise RuntimeError("Repair audit changed its exact revision transition.")
        responsibility = event.responsibility
        project_id = None
        action = None
        after_values: dict[str, object] = {"access_revision": event.after_revision}
        if isinstance(responsibility, GroupManagerRepairResponsibilityDTO):
            project_id = responsibility.project_id.value
            target_kind, target_id = "access_group", responsibility.access_group_id.value
            after_values.update(member=True, manager=True)
        else:
            target = responsibility.target
            action = responsibility.action_id.value
            if (
                isinstance(target, ProjectGrantTargetDTO)
                and action == ProjectAction.EDIT_PROJECT_METADATA.value
            ):
                await self._metadata_audit_writer.repaired(
                    ProjectMetadataAuthorityRepairedAuditEventDTO(
                        event.organization_id,
                        target.project_id,
                        event.recipient_id,
                        event.operation_id,
                        event.operator_label,
                        event.reason,
                        event.before_revision,
                        event.after_revision,
                    )
                )
                return
            if isinstance(target, OrganizationGrantTargetDTO):
                if target.organization_id != event.organization_id:
                    raise RuntimeError("Repair audit changed Organization scope.")
                target_kind, target_id = "organization", target.organization_id.value
            elif isinstance(target, ProjectGrantTargetDTO):
                project_id = target.project_id.value
                target_kind, target_id = "project", project_id
            elif isinstance(target, AccessGroupGrantTargetDTO):
                project_id = target.project_id.value
                target_kind, target_id = "access_group", target.access_group_id.value
            elif isinstance(target, ModelConnectionGrantTargetDTO):
                project_id = target.project_id.value
                target_kind, target_id = "model_connection", target.model_connection_id.value
            else:
                project_id = target.project_id.value
                target_kind, target_id = (
                    "application_account",
                    target.application_principal_id.value,
                )
            after_values["can_grant"] = True
        self._session.add(
            AccessAuditEventRow(
                id=uuid4(),
                organization_id=event.organization_id.value,
                project_id=project_id,
                actor_kind="operator",
                actor_reference=event.operator_label,
                affected_principal_id=event.recipient_id.value,
                event_type="stranded_authority_repaired",
                target_kind=target_kind,
                target_id=target_id,
                action=action,
                before_values={"access_revision": event.before_revision},
                after_values=after_values,
                reason=event.reason,
                correlation_id=event.operation_id.value,
            )
        )
        await self._session.flush()
