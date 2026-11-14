from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.model_connection_creation_facts_dto import (
    ModelConnectionCreationFactsDTO,
)
from inframeld_backend.access.application.dtos.model_connection_dto import ModelConnectionDTO
from inframeld_backend.access.domain.enums.model_connection_action import ModelConnectionAction
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.model_connection_action_grant_row import (
    ModelConnectionActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.model_connection_creation_result_row import (
    ModelConnectionCreationResultRow,
)
from inframeld_backend.access.infrastructure.rows.model_connection_row import ModelConnectionRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
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


class PostgresModelConnectionCreationWriter:
    """Save non-secret configuration, exact creator authority, and the original receipt atomically."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        actor: PrincipalId,
        facts: ModelConnectionCreationFactsDTO,
        operation_id: OperationId,
        connection: ModelConnectionDTO,
        initial_actions: tuple[ModelConnectionAction, ...],
    ) -> None:
        if (
            actor != facts.action.principal.id
            or connection.project_id != facts.project_id
            or initial_actions != tuple(ModelConnectionAction)
            or connection.credential_present
            or connection.credential_revision != 0
            or connection.connection_access_revision != 0
        ):
            raise RuntimeError("Model connection persistence changed the initial state.")
        project, organization = facts.project_id.value, facts.organization_id.value
        reservation = await self._session.scalar(
            select(IdempotencyReservationRow.operation_id).where(
                IdempotencyReservationRow.operation_id == operation_id.value,
                IdempotencyReservationRow.organization_id == organization,
                IdempotencyReservationRow.project_id == project,
                IdempotencyReservationRow.principal_id == actor.value,
                IdempotencyReservationRow.method == "POST",
                IdempotencyReservationRow.requested_route
                == f"/v1/projects/{project}/model-connections",
                IdempotencyReservationRow.lookup_authority_family
                == OperationLookupAuthorityFamily.PROJECT_ACTION_USE.value,
                IdempotencyReservationRow.lookup_action_id
                == ProjectAction.CREATE_MODEL_CONNECTIONS.value,
                IdempotencyReservationRow.state == OperationReservationState.IN_PROGRESS,
            )
        )
        if reservation is None:
            raise ConflictError("Model connection creation has no matching original reservation.")
        revision = await self._session.scalar(
            update(ProjectRow)
            .where(
                ProjectRow.id == project,
                ProjectRow.organization_id == organization,
                ProjectRow.status == ProjectStatus.ACTIVE,
                ProjectRow.access_revision == facts.access_revision,
            )
            .values(access_revision=facts.access_revision + 1)
            .returning(ProjectRow.access_revision)
        )
        if revision is None:
            raise StaleRevisionError()
        connection_id = connection.connection_id.value
        stored = await self._session.scalar(
            insert(ModelConnectionRow)
            .values(
                id=connection_id,
                project_id=project,
                organization_id=organization,
                name=connection.name.value,
                display_name=connection.display_name,
                provider=connection.access.provider.value,
                base_url=connection.access.base_url,
                api_version=connection.access.api_version,
                authentication=connection.access.authentication.value,
            )
            .on_conflict_do_nothing(
                index_elements=[ModelConnectionRow.project_id, ModelConnectionRow.name]
            )
            .returning(ModelConnectionRow.id)
        )
        if stored is None:
            raise ConflictError("The requested model connection Name is unavailable.")
        self._session.add_all(
            ModelConnectionActionGrantRow(
                project_id=project,
                model_connection_id=connection_id,
                recipient_principal_id=actor.value,
                recipient_kind=PrincipalKind.HUMAN,
                action=action.value,
                can_grant=True,
                assigned_by_principal_id=actor.value,
            )
            for action in initial_actions
        )
        self._session.add(
            ModelConnectionCreationResultRow(
                operation_id=operation_id.value,
                organization_id=organization,
                project_id=project,
                creator_principal_id=actor.value,
                model_connection_id=connection_id,
                name=connection.name.value,
                display_name=connection.display_name,
                provider=connection.access.provider.value,
                base_url=connection.access.base_url,
                api_version=connection.access.api_version,
                authentication=connection.access.authentication.value,
                before_revision=facts.access_revision,
                project_access_revision=revision,
                initial_actions=[action.value for action in initial_actions],
            )
        )
        self._session.add(
            AccessAuditEventRow(
                id=uuid4(),
                organization_id=organization,
                project_id=project,
                actor_kind="human",
                actor_principal_id=actor.value,
                event_type="model_connection_created",
                target_kind="model_connection",
                target_id=connection_id,
                correlation_id=operation_id.value,
                after_values={
                    "initial_actions": [action.value for action in initial_actions],
                    "project_access_revision": revision,
                },
            )
        )
        await self._session.flush()
