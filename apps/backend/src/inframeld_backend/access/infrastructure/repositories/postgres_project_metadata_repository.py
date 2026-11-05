from typing import override

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, AsyncSessionTransaction

from inframeld_backend.access.application.dtos.project_metadata_changed_audit_event_dto import (
    ProjectMetadataChangedAuditEventDTO,
)
from inframeld_backend.access.application.dtos.project_metadata_dto import ProjectMetadataDTO
from inframeld_backend.access.application.protocols.project_metadata_audit_writer import (
    ProjectMetadataAuditWriter,
)
from inframeld_backend.access.application.protocols.project_metadata_repository import (
    ProjectMetadataRepository,
)
from inframeld_backend.access.domain.entities.project_metadata import ProjectMetadata
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.mappers.postgres_project_metadata_mapper import (
    PostgresProjectMetadataMapper,
)
from inframeld_backend.access.infrastructure.rows.project_metadata_operation_result_row import (
    ProjectMetadataOperationResultRow,
)
from inframeld_backend.access.infrastructure.rows.project_name_reservation_row import (
    ProjectNameReservationRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    ResourceNotFoundError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)


class PostgresProjectMetadataRepository(ProjectMetadataRepository):
    """Persist a loaded transition, name history, bounded audit and original result together.

    One repository belongs to one active transaction. A failed save invalidates it.
    The application owns current authorization and commit or rollback.
    """

    def __init__(
        self, session: AsyncSession, metadata_audit_writer: ProjectMetadataAuditWriter
    ) -> None:
        self._session = session
        self._metadata_audit_writer = metadata_audit_writer
        self._transaction: AsyncSessionTransaction | None = None
        self._failed = False
        self._tracked: dict[
            tuple[OrganizationId, ProjectId], tuple[ProjectMetadata, ResourceName | None, str, int]
        ] = {}

    def _require_transaction(self) -> None:
        transaction = self._session.get_nested_transaction() or self._session.get_transaction()
        if (
            self._failed
            or transaction is None
            or not transaction.is_active
            or not self._session.is_active
        ):
            raise RuntimeError("Project metadata requires its active caller transaction.")
        if self._transaction is None:
            self._transaction = transaction
        elif self._transaction is not transaction:
            raise RuntimeError("Project metadata cannot reuse another transaction's objects.")

    @override
    async def get(
        self, *, organization_id: OrganizationId, project_id: ProjectId
    ) -> ProjectMetadata:
        self._require_transaction()
        key = (organization_id, project_id)
        tracked = self._tracked.get(key)
        if tracked is not None:
            return tracked[0]
        row = await self._session.scalar(
            select(ProjectRow)
            .where(
                ProjectRow.organization_id == organization_id.value,
                ProjectRow.id == project_id.value,
                ProjectRow.status == ProjectStatus.ACTIVE,
            )
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise ResourceNotFoundError()
        metadata = PostgresProjectMetadataMapper.from_row(row)
        self._tracked[key] = (metadata, metadata.name, metadata.display_name, metadata.revision)
        return metadata

    @override
    async def save(
        self,
        metadata: ProjectMetadata,
        *,
        expected_revision: int,
        actor_id: PrincipalId,
        operation_id: OperationId,
    ) -> None:
        try:
            self._require_transaction()
            tracked = self._tracked.get((metadata.organization_id, metadata.project_id))
            if tracked is None or tracked[0] is not metadata:
                raise RuntimeError("Save only the metadata aggregate loaded by this repository.")
            _, old_name, old_label, old_revision = tracked
            changed = (metadata.name, metadata.display_name) != (old_name, old_label)
            if expected_revision != old_revision or metadata.revision != old_revision + int(
                changed
            ):
                raise RuntimeError("The metadata transition changed its loaded revision meaning.")
            reservation = await self._session.scalar(
                select(IdempotencyReservationRow.operation_id).where(
                    IdempotencyReservationRow.operation_id == operation_id.value,
                    IdempotencyReservationRow.organization_id == metadata.organization_id.value,
                    IdempotencyReservationRow.project_id == metadata.project_id.value,
                    IdempotencyReservationRow.principal_id == actor_id.value,
                    IdempotencyReservationRow.state == OperationReservationState.IN_PROGRESS,
                    IdempotencyReservationRow.lookup_authority_family == "project_action_use",
                    IdempotencyReservationRow.lookup_action_id
                    == ProjectAction.EDIT_PROJECT_METADATA.value,
                    IdempotencyReservationRow.method == "PATCH",
                    IdempotencyReservationRow.requested_route
                    == "/v1/projects/{project_id}/metadata",
                )
            )
            if reservation is None:
                raise ConflictError("The metadata operation has no matching reservation.")

            updated = await self._session.scalar(
                update(ProjectRow)
                .where(
                    ProjectRow.organization_id == metadata.organization_id.value,
                    ProjectRow.id == metadata.project_id.value,
                    ProjectRow.status == ProjectStatus.ACTIVE,
                    ProjectRow.metadata_revision == expected_revision,
                )
                .values(
                    resource_name=None if metadata.name is None else metadata.name.value,
                    name=metadata.display_name,
                    metadata_revision=metadata.revision,
                )
                .returning(ProjectRow.id)
                .execution_options(synchronize_session=False)
            )
            if updated is None:
                raise StaleRevisionError()
            if metadata.name != old_name:
                await self._change_name(metadata, old_name)

            self._session.add(
                ProjectMetadataOperationResultRow(
                    operation_id=operation_id.value,
                    organization_id=metadata.organization_id.value,
                    project_id=metadata.project_id.value,
                    name=None if metadata.name is None else metadata.name.value,
                    display_name=metadata.display_name,
                    metadata_revision=metadata.revision,
                )
            )
            await self._metadata_audit_writer.changed(
                ProjectMetadataChangedAuditEventDTO(
                    organization_id=metadata.organization_id,
                    project_id=metadata.project_id,
                    actor_id=actor_id,
                    operation_id=operation_id,
                    before_revision=old_revision,
                    after_revision=metadata.revision,
                    name_changed=metadata.name != old_name,
                    display_name_changed=metadata.display_name != old_label,
                )
            )
            await self._session.flush()
            self._tracked[(metadata.organization_id, metadata.project_id)] = (
                metadata,
                metadata.name,
                metadata.display_name,
                metadata.revision,
            )
        except BaseException:
            self._failed = True
            raise

    async def _change_name(self, metadata: ProjectMetadata, old_name: ResourceName | None) -> None:
        """Replace the active name binding without losing its original Project ownership."""
        name = metadata.name
        if name is None:
            raise RuntimeError("A Project selector cannot be silently removed.")
        if old_name is not None:
            retired = await self._session.scalar(
                update(ProjectNameReservationRow)
                .where(
                    ProjectNameReservationRow.organization_id == metadata.organization_id.value,
                    ProjectNameReservationRow.project_id == metadata.project_id.value,
                    ProjectNameReservationRow.name == old_name.value,
                    ProjectNameReservationRow.retired.is_(False),
                )
                .values(retired=True, binding_revision=metadata.revision)
                .returning(ProjectNameReservationRow.name)
            )
            if retired is None:
                raise RuntimeError("The Project's current name has no matching reservation.")
        allocated = await self._session.scalar(
            insert(ProjectNameReservationRow)
            .values(
                organization_id=metadata.organization_id.value,
                project_id=metadata.project_id.value,
                name=name.value,
                binding_revision=metadata.revision,
                retired=False,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    ProjectNameReservationRow.organization_id,
                    ProjectNameReservationRow.name,
                ]
            )
            .returning(ProjectNameReservationRow.name)
        )
        if allocated is None:
            raise ConflictError("The requested Project name is unavailable.")

    @override
    async def original(
        self, *, organization_id: OrganizationId, project_id: ProjectId, operation_id: OperationId
    ) -> ProjectMetadataDTO:
        self._require_transaction()
        row = await self._session.scalar(
            select(ProjectMetadataOperationResultRow)
            .where(
                ProjectMetadataOperationResultRow.operation_id == operation_id.value,
                ProjectMetadataOperationResultRow.organization_id == organization_id.value,
                ProjectMetadataOperationResultRow.project_id == project_id.value,
            )
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise ConflictError("The original metadata outcome is unavailable.")
        return ProjectMetadataDTO(
            organization_id,
            project_id,
            None if row.name is None else ResourceName(row.name),
            row.display_name,
            row.metadata_revision,
        )
