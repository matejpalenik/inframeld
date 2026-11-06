from typing import override

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.access_action_grant_changed_audit_event_dto import (
    AccessActionGrantChangedAuditEventDTO,
)
from inframeld_backend.access.application.dtos.organization_action_grant_change_result_dto import (
    OrganizationActionGrantChangeResultDTO,
)
from inframeld_backend.access.application.dtos.organization_grant_management_facts_dto import (
    OrganizationGrantManagementFactsDTO,
)
from inframeld_backend.access.application.dtos.organization_grant_target_dto import (
    OrganizationGrantTargetDTO,
)
from inframeld_backend.access.application.protocols.audit_event_writer import AuditEventWriter
from inframeld_backend.access.application.protocols.organization_action_grant_writer import (
    OrganizationActionGrantWriter,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.value_objects.action_grant_state import ActionGrantState
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.infrastructure.rows.organization_action_grant_operation_result_row import (
    OrganizationActionGrantOperationResultRow,
)
from inframeld_backend.access.infrastructure.rows.organization_action_grant_row import (
    OrganizationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.shared.application.enums.http_method import HttpMethod
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
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)


class PostgresOrganizationActionGrantWriter(OrganizationActionGrantWriter):
    """Persist only the checked exact transition and original outcome in the caller transaction."""

    def __init__(self, session: AsyncSession, audit_event_writer: AuditEventWriter) -> None:
        self._session = session
        self._audit_event_writer = audit_event_writer

    @override
    async def save_change(
        self,
        *,
        facts: OrganizationGrantManagementFactsDTO,
        recipient_principal_id: PrincipalId,
        after: ActionGrantState,
        operation_id: OperationId,
    ) -> None:
        self._require_transaction()
        recipient = facts.recipient
        if (
            recipient is None
            or recipient.id != recipient_principal_id
            or recipient.organization_id != facts.organization_id
            or recipient.kind is not PrincipalKind.HUMAN
        ):
            raise RuntimeError("Organization grant persistence changed the checked recipient.")
        await self._require_bound_reservation(
            operation_id=operation_id,
            facts=facts,
            recipient_principal_id=recipient_principal_id,
            method=HttpMethod.DELETE if after.can_grant is None else HttpMethod.PUT,
            state=OperationReservationState.IN_PROGRESS,
        )
        scope = (
            OrganizationActionGrantRow.organization_id == facts.organization_id.value,
            OrganizationActionGrantRow.recipient_principal_id == recipient_principal_id.value,
            OrganizationActionGrantRow.recipient_kind == PrincipalKind.HUMAN,
            OrganizationActionGrantRow.action == facts.action_id.value,
        )
        current = await self._session.scalar(
            select(OrganizationActionGrantRow)
            .where(*scope)
            .execution_options(populate_existing=True)
        )
        before = current.can_grant if current is not None else None
        if before is not facts.assignment.can_grant:
            raise ConflictError("The Organization assignment changed before persistence.")
        revision = await self._session.scalar(
            select(OrganizationRow.access_revision).where(
                OrganizationRow.id == facts.organization_id.value
            )
        )
        if revision != facts.access_revision:
            raise StaleRevisionError()
        if after == facts.assignment:
            return

        advanced = await self._session.scalar(
            update(OrganizationRow)
            .where(
                OrganizationRow.id == facts.organization_id.value,
                OrganizationRow.access_revision == facts.access_revision,
                OrganizationRow.access_revision < RevisionValidation.MAX_VALUE,
            )
            .values(access_revision=OrganizationRow.access_revision + 1)
            .returning(OrganizationRow.access_revision)
        )
        if advanced != facts.access_revision + 1:
            raise ConflictError("The Organization revision cannot advance from its checked value.")
        if before is None:
            assert after.can_grant is not None
            self._session.add(
                OrganizationActionGrantRow(
                    organization_id=facts.organization_id.value,
                    recipient_principal_id=recipient_principal_id.value,
                    recipient_kind=PrincipalKind.HUMAN,
                    action=facts.action_id.value,
                    can_grant=after.can_grant,
                    assigned_by_principal_id=facts.actor.id.value,
                )
            )
        elif after.can_grant is None:
            removed = await self._session.scalar(
                delete(OrganizationActionGrantRow)
                .where(*scope, OrganizationActionGrantRow.can_grant.is_(before))
                .returning(OrganizationActionGrantRow.recipient_principal_id)
            )
            if removed is None:
                raise ConflictError("The Organization assignment changed before removal.")
        else:
            changed = await self._session.scalar(
                update(OrganizationActionGrantRow)
                .where(*scope, OrganizationActionGrantRow.can_grant.is_(before))
                .values(can_grant=after.can_grant)
                .returning(OrganizationActionGrantRow.recipient_principal_id)
            )
            if changed is None:
                raise ConflictError("The Organization assignment changed before replacement.")
        await self._session.flush()
        await self._audit_event_writer.append(
            AccessActionGrantChangedAuditEventDTO(
                organization_id=facts.organization_id,
                target=OrganizationGrantTargetDTO(organization_id=facts.organization_id),
                actor_principal_id=facts.actor.id,
                recipient_principal_id=recipient_principal_id,
                action_id=facts.action_id,
                before_can_grant=before,
                can_grant=after.can_grant,
                operation_id=operation_id,
            )
        )

    @override
    async def save_result(
        self,
        *,
        result: OrganizationActionGrantChangeResultDTO,
        before_revision: int,
        before_can_grant: bool | None,
    ) -> None:
        self._require_transaction()
        changed = before_can_grant is not result.can_grant
        expected_status = (
            201 if result.method is HttpMethod.PUT and before_can_grant is None else 200
        )
        if (
            result.changed is not changed
            or result.access_revision != before_revision + int(changed)
            or not 0 <= before_revision <= result.access_revision <= RevisionValidation.MAX_VALUE
            or result.status_code != expected_status
            or (result.method is HttpMethod.PUT) != (result.can_grant is not None)
        ):
            raise ConflictError("The Organization grant receipt is incoherent.")
        stored = await self._session.get(
            IdempotencyReservationRow, result.operation.operation_id.value, populate_existing=True
        )
        route = f"/v1/organizations/{result.organization_id.value}/grants/{result.recipient_principal_id.value}/{result.action_id.value}"
        if (
            stored is None
            or stored.organization_id != result.organization_id.value
            or stored.project_id is not None
            or stored.principal_id != result.actor_principal_id.value
            or stored.method != result.method
            or stored.requested_route != route
            or stored.lookup_authority_family
            != OperationLookupAuthorityFamily.ORGANIZATION_GRANT_READ
            or stored.lookup_action_id != result.action_id.value
            or stored.state is not OperationReservationState.REPLAYABLE
            or stored.replay_kind is not OperationReplayKind.SAFE_RESULT
            or stored.expires_at != result.operation.expires_at
        ):
            raise ConflictError("The Organization receipt changed its original reservation.")
        self._session.add(
            OrganizationActionGrantOperationResultRow(
                operation_id=result.operation.operation_id.value,
                installation_id=result.installation_id.value,
                organization_id=result.organization_id.value,
                actor_principal_id=result.actor_principal_id.value,
                recipient_principal_id=result.recipient_principal_id.value,
                action_id=result.action_id.value,
                method=result.method.value,
                before_revision=before_revision,
                access_revision=result.access_revision,
                before_can_grant=before_can_grant,
                can_grant=result.can_grant,
                changed=result.changed,
                status_code=result.status_code,
            )
        )
        await self._session.flush()

    def _require_transaction(self) -> None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError(
                "Organization grant persistence requires the active caller transaction."
            )

    async def _require_bound_reservation(
        self,
        *,
        operation_id: OperationId,
        facts: OrganizationGrantManagementFactsDTO,
        recipient_principal_id: PrincipalId,
        method: HttpMethod,
        state: OperationReservationState,
    ) -> None:
        """Match the original exact scope before changing a grant or its revision."""
        stored = await self._session.get(
            IdempotencyReservationRow, operation_id.value, populate_existing=True
        )
        route = f"/v1/organizations/{facts.organization_id.value}/grants/{recipient_principal_id.value}/{facts.action_id.value}"
        if (
            stored is None
            or stored.organization_id != facts.organization_id.value
            or stored.project_id is not None
            or stored.principal_id != facts.actor.id.value
            or stored.method != method
            or stored.requested_route != route
            or stored.lookup_authority_family
            != OperationLookupAuthorityFamily.ORGANIZATION_GRANT_READ
            or stored.lookup_action_id != facts.action_id.value
            or stored.state is not state
        ):
            raise ConflictError("The Organization grant changed its original reservation binding.")
