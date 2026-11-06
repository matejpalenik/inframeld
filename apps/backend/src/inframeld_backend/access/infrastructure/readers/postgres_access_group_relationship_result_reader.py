from typing import override

from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.commands.change_access_group_relationship_command import (
    ChangeAccessGroupRelationshipCommand,
)
from inframeld_backend.access.application.dtos.access_group_change_facts_dto import (
    AccessGroupChangeFactsDTO,
)
from inframeld_backend.access.application.dtos.access_group_relationship_result_dto import (
    AccessGroupRelationshipResultDTO,
)
from inframeld_backend.access.application.protocols.access_group_relationship_result_reader import (
    AccessGroupRelationshipResultReader,
)
from inframeld_backend.access.domain.value_objects.access_group_relationships import (
    AccessGroupRelationships,
)
from inframeld_backend.access.infrastructure.rows.access_group_relationship_result_row import (
    AccessGroupRelationshipResultRow,
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
)
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)


class PostgresAccessGroupRelationshipResultReader(AccessGroupRelationshipResultReader):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def original(
        self,
        *,
        facts: AccessGroupChangeFactsDTO,
        command: ChangeAccessGroupRelationshipCommand,
        operation: CompletedSynchronousOperationDTO,
    ) -> AccessGroupRelationshipResultDTO:
        try:
            if not self._session.in_transaction() or not self._session.is_active:
                raise RuntimeError("Group replay requires the active caller transaction.")
            native, saved, kind = (
                IdempotencyReservationRow,
                AccessGroupRelationshipResultRow,
                command.change_kind,
            )
            route = f"/v1/projects/{command.project_id.value}/access-groups/{command.group_id.value}/{kind.collection}/{command.principal_id.value}"
            row = await self._session.scalar(
                select(saved)
                .join(native, native.operation_id == saved.operation_id)
                .where(
                    saved.operation_id == operation.operation_id.value,
                    saved.organization_id == facts.organization_id.value,
                    saved.project_id == command.project_id.value,
                    saved.group_id == command.group_id.value,
                    saved.actor_principal_id == facts.action.principal.id.value,
                    saved.principal_id == command.principal_id.value,
                    saved.change_kind == kind.value,
                    saved.before_revision == command.expected_access_revision,
                    native.organization_id == saved.organization_id,
                    native.project_id == saved.project_id,
                    native.principal_id == saved.actor_principal_id,
                    native.method == kind.http_method,
                    native.requested_route == route,
                    native.lookup_authority_family.is_(None),
                    native.lookup_action_id.is_(None),
                    native.state == OperationReservationState.REPLAYABLE,
                    native.replay_kind == OperationReplayKind.SAFE_RESULT,
                    native.expires_at > func.clock_timestamp(),
                )
                .execution_options(populate_existing=True, autoflush=False)
            )
            if row is None:
                raise ConflictError("The original group transition is unavailable.")
            try:
                return AccessGroupRelationshipResultDTO(
                    organization_id=facts.organization_id,
                    project_id=facts.project_id,
                    group_id=facts.group_id,
                    actor_principal_id=facts.action.principal.id,
                    principal_id=command.principal_id,
                    change_kind=kind,
                    access_revision=row.access_revision,
                    changed=row.changed,
                    relationships=AccessGroupRelationships(member=row.member, manager=row.manager),
                    status_code=row.status_code,
                    operation=operation,
                )
            except (ValueError, TypeError):
                raise ConflictError("The original group transition is incoherent.") from None
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None
