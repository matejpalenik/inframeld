from typing import Literal, override
from uuid import uuid4

from sqlalchemy import and_, exists, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.mappers.postgres_project_actor_mapper import (
    PostgresProjectActorMapper,
)
from inframeld_backend.access.infrastructure.readers.model_connection_reference_queries import (
    ModelConnectionReferenceQueries,
)
from inframeld_backend.access.infrastructure.readers.project_actor_queries import (
    ProjectActorQueries,
)
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.indexing.application.dtos.embedding_profile_creation_dto import (
    EmbeddingProfileCreationDTO,
)
from inframeld_backend.indexing.application.dtos.embedding_profile_creation_facts_dto import (
    EmbeddingProfileCreationFactsDTO,
)
from inframeld_backend.indexing.application.dtos.embedding_profile_dto import EmbeddingProfileDTO
from inframeld_backend.indexing.application.protocols.embedding_profile_creation_repository import (
    EmbeddingProfileCreationRepository,
)
from inframeld_backend.indexing.domain.enums.embedding_profile_action import (
    EmbeddingProfileAction,
)
from inframeld_backend.indexing.infrastructure.mappers.postgres_embedding_profile_mapper import (
    PostgresEmbeddingProfileMapper,
)
from inframeld_backend.indexing.infrastructure.readers.processing_profile_project_lock import (
    ProcessingProfileProjectLock,
)
from inframeld_backend.indexing.infrastructure.rows.embedding_profile_action_grant_row import (
    EmbeddingProfileActionGrantRow,
)
from inframeld_backend.indexing.infrastructure.rows.embedding_profile_creation_result_row import (
    EmbeddingProfileCreationResultRow,
)
from inframeld_backend.indexing.infrastructure.rows.embedding_profile_row import (
    EmbeddingProfileRow,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)

_CREATE_ACTION = ProjectAction.CREATE_EMBEDDING_PROFILES.value
_INITIAL_ACTIONS = tuple(EmbeddingProfileAction)


class PostgresEmbeddingProfileCreationRepository(EmbeddingProfileCreationRepository):
    """Store profile creation and original results within the checked Project turn."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def lock_for_creation(
        self, *, access: AccessContextDTO, project_id: ProjectId
    ) -> EmbeddingProfileCreationFactsDTO | None:
        try:
            organization = await ProcessingProfileProjectLock.acquire(
                self._session, access.actor_principal_id, project_id, shared=False
            )
            if organization is None:
                return None

            granted = (
                exists()
                .where(
                    ProjectActionGrantRow.project_id == ProjectRow.id,
                    ProjectActionGrantRow.recipient_principal_id == PrincipalRow.id,
                    ProjectActionGrantRow.recipient_kind == PrincipalRow.kind,
                    ProjectActionGrantRow.action == _CREATE_ACTION,
                )
                .correlate(PrincipalRow, ProjectRow)
            )
            record = (
                (
                    await self._session.execute(
                        ProjectActorQueries.header(access, project_id).add_columns(granted)
                    )
                )
                .tuples()
                .one_or_none()
            )
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None

        if record is None:
            return None
        principal, project, installation, member, recovering, linked, version, has_grant = record
        if installation is None:
            raise DependencyUnavailableError("The installation identity is unavailable.")
        if project.organization_id != organization:
            raise RuntimeError("Embedding Profile creation changed the locked Organization.")
        return EmbeddingProfileCreationFactsDTO(
            organization_id=OrganizationId(organization),
            project_id=ProjectId(project.id),
            access_revision=project.access_revision,
            action=PostgresProjectActorMapper.action(
                access=access,
                principal=principal,
                project=project,
                member=member,
                recovering=recovering,
                linked=linked,
                version=version,
                granted=has_grant,
            ),
        )

    @override
    async def lock_live_selection(
        self, *, facts: EmbeddingProfileCreationFactsDTO, connection_id: ModelConnectionId
    ) -> bool:
        self._require_transaction()
        try:
            return await ModelConnectionReferenceQueries.has_live_target(
                self._session, facts.organization_id, facts.project_id, connection_id
            )
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None

    @override
    async def original(
        self,
        *,
        access: AccessContextDTO,
        facts: EmbeddingProfileCreationFactsDTO,
        operation: CompletedSynchronousOperationDTO,
    ) -> EmbeddingProfileCreationDTO:
        self._require_transaction()
        receipt = EmbeddingProfileCreationResultRow
        profile_row = EmbeddingProfileRow
        try:
            record = (
                (
                    await self._session.execute(
                        select(receipt, profile_row)
                        .join(
                            profile_row,
                            and_(
                                profile_row.project_id == receipt.project_id,
                                profile_row.organization_id == receipt.organization_id,
                                profile_row.id == receipt.embedding_profile_id,
                            ),
                        )
                        .where(
                            receipt.operation_id == operation.operation_id.value,
                            receipt.organization_id == facts.organization_id.value,
                            receipt.project_id == facts.project_id.value,
                            receipt.creator_principal_id == access.actor_principal_id.value,
                        )
                        .execution_options(populate_existing=True, autoflush=False)
                    )
                )
                .tuples()
                .one_or_none()
            )
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None

        if record is None:
            raise ConflictError("The original Embedding Profile creation result is unavailable.")
        original, profile = record
        if (
            original.initial_actions != [action.value for action in _INITIAL_ACTIONS]
            or not original.can_grant
            or original.project_access_revision != original.before_revision + 1
        ):
            raise ConflictError("The original Embedding Profile creation result is incoherent.")
        try:
            saved_profile = PostgresEmbeddingProfileMapper.profile(profile)
        except ValueError:
            raise ConflictError(
                "The original Embedding Profile definition is incoherent."
            ) from None
        return EmbeddingProfileCreationDTO(
            profile=saved_profile,
            operation=operation,
            project_access_revision=original.project_access_revision,
            initial_actions=_INITIAL_ACTIONS,
            can_grant=True,
        )

    @override
    async def save(
        self,
        *,
        access: AccessContextDTO,
        facts: EmbeddingProfileCreationFactsDTO,
        operation_id: OperationId,
        profile: EmbeddingProfileDTO,
        initial_actions: tuple[EmbeddingProfileAction, ...],
        can_grant: Literal[True],
    ) -> None:
        self._require_transaction()
        principal = facts.action.principal
        if (
            principal.id != access.actor_principal_id
            or principal.organization_id != facts.organization_id
            or principal.kind is not PrincipalKind.HUMAN
            or profile.layout.organization_id != facts.organization_id
            or profile.layout.project_id != facts.project_id
            or not profile.has_coherent_layout()
            or initial_actions != _INITIAL_ACTIONS
            or can_grant is not True
        ):
            raise RuntimeError("Embedding Profile persistence changed the initial state.")

        try:
            await self._save_new(facts, operation_id, profile)
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None

    def _require_transaction(self) -> None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Embedding Profile creation requires an active caller transaction.")

    async def _save_new(
        self,
        facts: EmbeddingProfileCreationFactsDTO,
        operation_id: OperationId,
        profile: EmbeddingProfileDTO,
    ) -> None:
        project, organization = facts.project_id.value, facts.organization_id.value
        actor = facts.action.principal.id.value
        reservation = await self._session.scalar(
            select(IdempotencyReservationRow.operation_id).where(
                IdempotencyReservationRow.operation_id == operation_id.value,
                IdempotencyReservationRow.organization_id == organization,
                IdempotencyReservationRow.project_id == project,
                IdempotencyReservationRow.principal_id == actor,
                IdempotencyReservationRow.method == HttpMethod.POST.value,
                IdempotencyReservationRow.requested_route
                == f"/v1/projects/{project}/embedding-profiles",
                IdempotencyReservationRow.lookup_authority_family
                == OperationLookupAuthorityFamily.PROJECT_ACTION_USE.value,
                IdempotencyReservationRow.lookup_action_id == _CREATE_ACTION,
                IdempotencyReservationRow.state == OperationReservationState.IN_PROGRESS,
            )
        )
        if reservation is None:
            raise ConflictError("Embedding Profile creation has no matching original reservation.")

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

        stored = await self._session.scalar(
            insert(EmbeddingProfileRow)
            .values(PostgresEmbeddingProfileMapper.insert_values(profile))
            .on_conflict_do_nothing(
                index_elements=[EmbeddingProfileRow.project_id, EmbeddingProfileRow.name]
            )
            .returning(EmbeddingProfileRow.id)
        )
        if stored is None:
            raise ConflictError("The requested Embedding Profile Name is unavailable.")

        profile_id = profile.layout.embedding_profile_id.value
        actions = [action.value for action in _INITIAL_ACTIONS]
        self._session.add_all(
            EmbeddingProfileActionGrantRow(
                project_id=project,
                embedding_profile_id=profile_id,
                recipient_principal_id=actor,
                recipient_kind=PrincipalKind.HUMAN,
                action=action,
                can_grant=True,
                assigned_by_principal_id=actor,
            )
            for action in actions
        )
        self._session.add(
            EmbeddingProfileCreationResultRow(
                operation_id=operation_id.value,
                organization_id=organization,
                project_id=project,
                creator_principal_id=actor,
                embedding_profile_id=profile_id,
                before_revision=facts.access_revision,
                project_access_revision=revision,
                initial_actions=actions,
                can_grant=True,
            )
        )
        self._session.add(
            AccessAuditEventRow(
                id=uuid4(),
                organization_id=organization,
                project_id=project,
                actor_kind=PrincipalKind.HUMAN.value,
                actor_principal_id=actor,
                event_type="embedding_profile_created",
                target_kind="embedding_profile",
                target_id=profile_id,
                correlation_id=operation_id.value,
                after_values={"initial_actions": actions, "project_access_revision": revision},
            )
        )
        await self._session.flush()
