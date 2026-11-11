import asyncio
from typing import override
from uuid import uuid4

from sqlalchemy import DateTime, String, delete, func, select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.project_upload_default_record_dto import (
    ProjectUploadDefaultRecordDTO,
)
from inframeld_backend.access.application.protocols.project_upload_default_repository import (
    ProjectUploadDefaultRepository,
)
from inframeld_backend.access.domain.entities.project_upload_default import ProjectUploadDefault
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.domain.value_objects.upload_audience import UploadAudience
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.access_group_row import AccessGroupRow
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.rows.project_upload_default_group_row import (
    ProjectUploadDefaultGroupRow,
)
from inframeld_backend.access.infrastructure.rows.project_upload_default_result_row import (
    ProjectUploadDefaultResultRow,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
    ResourceNotFoundError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)


class PostgresProjectUploadDefaultRepository(ProjectUploadDefaultRepository):
    """Save checked defaults and immutable safe originals in the owning transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _require_transaction(self) -> None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Upload-default persistence requires the active caller transaction.")
        if (
            await self._session.scalar(
                select(func.current_setting("transaction_isolation", type_=String()))
            )
            != "read committed"
        ):
            raise RuntimeError("Upload-default persistence requires READ COMMITTED isolation.")

    @override
    async def get(
        self, *, organization_id: OrganizationId, project_id: ProjectId
    ) -> ProjectUploadDefault:
        try:
            async with asyncio.timeout(5):
                await self._require_transaction()
                revision = await self._session.scalar(
                    select(ProjectRow.access_revision)
                    .where(
                        ProjectRow.organization_id == organization_id.value,
                        ProjectRow.id == project_id.value,
                    )
                    .execution_options(populate_existing=True, autoflush=False)
                )
                if revision is None:
                    raise ResourceNotFoundError()
                return ProjectUploadDefault(
                    organization_id=organization_id,
                    project_id=project_id,
                    audience=await self._stored_audience(organization_id, project_id),
                    access_revision=revision,
                )
        except (TimeoutError, OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None

    async def _stored_audience(
        self, organization_id: OrganizationId, project_id: ProjectId
    ) -> UploadAudience | None:
        rows = tuple(
            await self._session.scalars(
                select(ProjectUploadDefaultGroupRow)
                .where(ProjectUploadDefaultGroupRow.project_id == project_id.value)
                .order_by(ProjectUploadDefaultGroupRow.group_id)
                .execution_options(populate_existing=True, autoflush=False)
            )
        )
        if any(row.organization_id != organization_id.value for row in rows):
            raise ConflictError("The stored upload-default scope is incoherent.")
        if not rows:
            return None
        return UploadAudience(tuple(AccessGroupId(row.group_id) for row in rows))

    @override
    async def save(
        self,
        default: ProjectUploadDefault,
        *,
        original: ProjectUploadDefaultRecordDTO,
        fingerprint: RequestFingerprint,
    ) -> None:
        try:
            async with asyncio.timeout(5):
                await self._save(default, original, fingerprint)
        except IntegrityError:
            raise ConflictError("Stored default scope or original binding conflicts.") from None
        except (TimeoutError, OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None

    async def _save(
        self,
        default: ProjectUploadDefault,
        original: ProjectUploadDefaultRecordDTO,
        fingerprint: RequestFingerprint,
    ) -> None:
        await self._require_transaction()
        RevisionValidation.require(original.before_revision)
        RevisionValidation.require(original.access_revision)
        changed = original.before_audience != original.audience
        if (
            default.organization_id != original.organization_id
            or default.project_id != original.project_id
            or default.audience != original.audience
            or default.access_revision != original.access_revision
            or original.access_revision != original.before_revision + int(changed)
        ):
            raise ConflictError("The saved default changed its checked transition.")
        route = f"/v1/projects/{original.project_id.value}/upload-defaults"
        parent = IdempotencyReservationRow
        reservation = await self._session.scalar(
            select(parent.operation_id).where(
                parent.operation_id == original.operation_id.value,
                parent.organization_id == original.organization_id.value,
                parent.project_id == original.project_id.value,
                parent.principal_id == original.actor_principal_id.value,
                parent.method == "PUT",
                parent.requested_route == route,
                parent.request_fingerprint == fingerprint.value,
                parent.lookup_authority_family.is_(None),
                parent.lookup_action_id.is_(None),
                parent.state == OperationReservationState.IN_PROGRESS,
                parent.replay_kind.is_(None),
                parent.expires_at.is_(None),
            )
        )
        if reservation is None:
            raise ConflictError("Upload-default persistence has no matching original reservation.")
        if (
            await self._session.scalar(
                select(OrganizationRow.id)
                .where(OrganizationRow.id == original.organization_id.value)
                .with_for_update(read=True)
            )
            is None
        ):
            raise ConflictError("The checked Organization is unavailable.")
        project = await self._session.scalar(
            select(ProjectRow)
            .where(
                ProjectRow.id == original.project_id.value,
                ProjectRow.organization_id == original.organization_id.value,
                ProjectRow.status == ProjectStatus.ACTIVE,
            )
            .with_for_update()
            .execution_options(populate_existing=True, autoflush=False)
        )
        if project is None:
            raise ConflictError("The checked Project is unavailable.")
        if project.access_revision != original.before_revision:
            raise StaleRevisionError()
        if (
            await self._stored_audience(original.organization_id, original.project_id)
            != original.before_audience
        ):
            raise ConflictError("The saved upload-default snapshot changed.")
        identifiers = tuple(group.value for group in original.audience.group_ids)
        groups = set(
            await self._session.scalars(
                select(AccessGroupRow.id).where(
                    AccessGroupRow.project_id == original.project_id.value,
                    AccessGroupRow.id.in_(identifiers),
                )
            )
        )
        if groups != set(identifiers):
            raise ConflictError("The checked audience is unavailable.")
        if changed:
            if (
                await self._session.scalar(
                    update(ProjectRow)
                    .where(
                        ProjectRow.id == original.project_id.value,
                        ProjectRow.organization_id == original.organization_id.value,
                        ProjectRow.access_revision == original.before_revision,
                        ProjectRow.access_revision < RevisionValidation.MAX_VALUE,
                        ProjectRow.status == ProjectStatus.ACTIVE,
                    )
                    .values(access_revision=original.access_revision)
                    .returning(ProjectRow.id)
                )
                is None
            ):
                raise StaleRevisionError()
            await self._session.execute(
                delete(ProjectUploadDefaultGroupRow).where(
                    ProjectUploadDefaultGroupRow.project_id == original.project_id.value,
                    ProjectUploadDefaultGroupRow.organization_id == original.organization_id.value,
                )
            )
            self._session.add_all(
                [
                    ProjectUploadDefaultGroupRow(
                        organization_id=original.organization_id.value,
                        project_id=original.project_id.value,
                        group_id=identifier,
                    )
                    for identifier in identifiers
                ]
            )
            self._session.add(
                AccessAuditEventRow(
                    id=uuid4(),
                    organization_id=original.organization_id.value,
                    project_id=original.project_id.value,
                    actor_kind=PrincipalKind.HUMAN.value,
                    actor_principal_id=original.actor_principal_id.value,
                    event_type="project_upload_default_changed",
                    target_kind="project",
                    target_id=original.project_id.value,
                    action="manage-upload-defaults",
                    before_values={
                        "groupIds": None
                        if original.before_audience is None
                        else [str(group.value) for group in original.before_audience.group_ids],
                        "accessRevision": original.before_revision,
                    },
                    after_values={
                        "groupIds": [str(group.value) for group in original.audience.group_ids],
                        "accessRevision": original.access_revision,
                    },
                    correlation_id=original.operation_id.value,
                )
            )
        self._session.add(
            ProjectUploadDefaultResultRow(
                operation_id=original.operation_id.value,
                organization_id=original.organization_id.value,
                project_id=original.project_id.value,
                actor_principal_id=original.actor_principal_id.value,
                before_revision=original.before_revision,
                access_revision=original.access_revision,
                before_group_ids=None
                if original.before_audience is None
                else [group.value for group in original.before_audience.group_ids],
                group_ids=list(identifiers),
            )
        )
        await self._session.flush()

    @override
    async def original(
        self,
        *,
        organization_id: OrganizationId,
        project_id: ProjectId,
        actor_principal_id: PrincipalId,
        operation: CompletedSynchronousOperationDTO,
    ) -> ProjectUploadDefaultRecordDTO | None:
        try:
            async with asyncio.timeout(5):
                await self._require_transaction()
                if (
                    operation.replay_kind is not OperationReplayKind.SAFE_RESULT
                    or operation.expires_at.utcoffset() is None
                ):
                    raise ConflictError(
                        "Upload-default recovery requires an authentic safe original."
                    )
                row, parent = ProjectUploadDefaultResultRow, IdempotencyReservationRow
                stored = await self._session.scalar(
                    select(row)
                    .join(parent, parent.operation_id == row.operation_id)
                    .where(
                        row.operation_id == operation.operation_id.value,
                        row.organization_id == organization_id.value,
                        row.project_id == project_id.value,
                        row.actor_principal_id == actor_principal_id.value,
                        parent.organization_id == row.organization_id,
                        parent.project_id == row.project_id,
                        parent.principal_id == row.actor_principal_id,
                        parent.method == "PUT",
                        parent.requested_route
                        == f"/v1/projects/{project_id.value}/upload-defaults",
                        parent.lookup_authority_family.is_(None),
                        parent.lookup_action_id.is_(None),
                        parent.state == OperationReservationState.REPLAYABLE,
                        parent.replay_kind == OperationReplayKind.SAFE_RESULT,
                        parent.expires_at == operation.expires_at,
                        parent.expires_at > func.clock_timestamp(type_=DateTime(timezone=True)),
                    )
                    .execution_options(populate_existing=True, autoflush=False)
                )
                if stored is None:
                    return None
                try:
                    before = (
                        None
                        if stored.before_group_ids is None
                        else UploadAudience(
                            tuple(AccessGroupId(value) for value in stored.before_group_ids)
                        )
                    )
                    after = UploadAudience(
                        tuple(AccessGroupId(value) for value in stored.group_ids)
                    )
                    RevisionValidation.require(stored.before_revision)
                    RevisionValidation.require(stored.access_revision)
                    if (
                        stored.access_revision != stored.before_revision + int(before != after)
                        or list(group.value for group in after.group_ids) != stored.group_ids
                        or (
                            before is not None
                            and list(group.value for group in before.group_ids)
                            != stored.before_group_ids
                        )
                    ):
                        raise ValueError("Incoherent original audience or revision.")
                    return ProjectUploadDefaultRecordDTO(
                        operation.operation_id,
                        organization_id,
                        project_id,
                        actor_principal_id,
                        stored.before_revision,
                        stored.access_revision,
                        before,
                        after,
                    )
                except (ValueError, TypeError):
                    raise ConflictError(
                        "The original upload-default result is incoherent."
                    ) from None
        except (TimeoutError, OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None
