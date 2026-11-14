from uuid import uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.processing_profile_grant_facts_dto import (
    ProcessingProfileGrantFactsDTO,
)
from inframeld_backend.access.application.dtos.processing_profile_grant_result_dto import (
    ProcessingProfileGrantResultDTO,
)
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.action_grant_state import ActionGrantState
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.processing_profile_grant_result_row import (
    ProcessingProfileGrantResultRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.indexing.infrastructure.rows.processing_profile_action_grant_row import (
    ProcessingProfileActionGrantRow,
)
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)


class PostgresProcessingProfileActionGrantWriter:
    """Persist one exact checked action under its owning Project Access turn."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_change(
        self,
        facts: ProcessingProfileGrantFactsDTO,
        recipient_id: PrincipalId,
        after: ActionGrantState,
        operation_id: OperationId,
    ) -> None:
        await self._require_binding(
            facts,
            recipient_id,
            after.can_grant,
            operation_id,
            OperationReservationState.IN_PROGRESS,
        )
        await self.apply_assignment(facts, recipient_id, after, operation_id)

    async def apply_assignment(
        self,
        facts: ProcessingProfileGrantFactsDTO,
        recipient_id: PrincipalId,
        after: ActionGrantState,
        operation_id: OperationId,
    ) -> int:
        """Apply a transition whose operation binding was already checked by its caller."""
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError(
                "Processing Profile grant persistence requires the caller transaction."
            )
        recipient = facts.recipient
        if (
            recipient is None
            or recipient.id != recipient_id
            or recipient.organization_id != facts.organization_id
        ):
            raise RuntimeError("Processing Profile grant persistence changed its exact recipient.")
        before = facts.assignment.can_grant
        if before is after.can_grant:
            return facts.access_revision
        project, profile = facts.project_id.value, facts.processing_profile_id.value
        grant = ProcessingProfileActionGrantRow
        scope = (
            grant.project_id == project,
            grant.processing_profile_id == profile,
            grant.recipient_principal_id == recipient.id.value,
            grant.recipient_kind == recipient.kind,
            grant.action == facts.action.value,
        )
        if before is None:
            inserted = await self._session.scalar(
                insert(grant)
                .values(
                    project_id=project,
                    processing_profile_id=profile,
                    recipient_principal_id=recipient.id.value,
                    recipient_kind=recipient.kind,
                    action=facts.action.value,
                    can_grant=after.can_grant,
                    assigned_by_principal_id=facts.actor.principal.id.value,
                )
                .on_conflict_do_nothing()
                .returning(grant.recipient_principal_id)
            )
        elif after.can_grant is None:
            inserted = await self._session.scalar(
                delete(grant)
                .where(*scope, grant.can_grant.is_(before))
                .returning(grant.recipient_principal_id)
            )
        else:
            inserted = await self._session.scalar(
                update(grant)
                .where(*scope, grant.can_grant.is_(before))
                .values(can_grant=after.can_grant)
                .returning(grant.recipient_principal_id)
            )
        if inserted != recipient.id.value:
            raise ConflictError("The checked Processing Profile assignment changed.")
        next_revision = facts.access_revision + 1
        revision = await self._session.scalar(
            update(ProjectRow)
            .where(
                ProjectRow.id == project,
                ProjectRow.organization_id == facts.organization_id.value,
                ProjectRow.status == ProjectStatus.ACTIVE,
                ProjectRow.access_revision == facts.access_revision,
            )
            .values(access_revision=next_revision)
            .returning(ProjectRow.access_revision)
        )
        if revision is None or revision != next_revision:
            raise StaleRevisionError()
        self._session.add(
            AccessAuditEventRow(
                id=uuid4(),
                organization_id=facts.organization_id.value,
                project_id=project,
                actor_kind="human",
                actor_principal_id=facts.actor.principal.id.value,
                affected_principal_id=recipient.id.value,
                event_type="action_grant_changed",
                target_kind="processing_profile",
                target_id=profile,
                action=facts.action.value,
                before_values={"can_grant": before, "access_revision": facts.access_revision},
                after_values={"can_grant": after.can_grant, "access_revision": revision},
                correlation_id=operation_id.value,
            )
        )
        await self._session.flush()
        return revision

    async def save_result(
        self, facts: ProcessingProfileGrantFactsDTO, result: ProcessingProfileGrantResultDTO
    ) -> None:
        await self._require_binding(
            facts,
            result.recipient_id,
            result.can_grant,
            result.operation.operation_id,
            OperationReservationState.REPLAYABLE,
        )
        if (
            not result.operation.created
            or result.operation.replay_kind is not OperationReplayKind.SAFE_RESULT
        ):
            raise ConflictError("Processing Profile grant has no safe original operation.")
        self._session.add(
            ProcessingProfileGrantResultRow(
                operation_id=result.operation.operation_id.value,
                organization_id=facts.organization_id.value,
                project_id=facts.project_id.value,
                processing_profile_id=facts.processing_profile_id.value,
                actor_principal_id=facts.actor.principal.id.value,
                recipient_principal_id=result.recipient_id.value,
                action=facts.action.value,
                before_can_grant=facts.assignment.can_grant,
                can_grant=result.can_grant,
                before_revision=facts.access_revision,
                access_revision=result.access_revision,
                status_code=result.status_code,
            )
        )
        await self._session.flush()

    async def _require_binding(
        self,
        facts: ProcessingProfileGrantFactsDTO,
        recipient_id: PrincipalId,
        can_grant: bool | None,
        operation_id: OperationId,
        state: OperationReservationState,
    ) -> None:
        route = f"/v1/processing-profiles/{facts.processing_profile_id.value}/grants/{recipient_id.value}/{facts.action.value}"
        reservation = await self._session.scalar(
            select(IdempotencyReservationRow.operation_id).where(
                IdempotencyReservationRow.operation_id == operation_id.value,
                IdempotencyReservationRow.organization_id == facts.organization_id.value,
                IdempotencyReservationRow.project_id == facts.project_id.value,
                IdempotencyReservationRow.principal_id == facts.actor.principal.id.value,
                IdempotencyReservationRow.method == ("DELETE" if can_grant is None else "PUT"),
                IdempotencyReservationRow.requested_route == route,
                IdempotencyReservationRow.lookup_authority_family
                == OperationLookupAuthorityFamily.PROCESSING_PROFILE_GRANT_READ.value,
                IdempotencyReservationRow.lookup_action_id == facts.action.value,
                IdempotencyReservationRow.state == state,
            )
        )
        if reservation is None:
            raise ConflictError("Processing Profile grant has no matching original reservation.")
