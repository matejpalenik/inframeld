from dataclasses import replace
from uuid import uuid4

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_key_authentication_dto import (
    ApplicationKeyAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.application_key_verification_profile_dto import (
    ApplicationKeyVerificationProfileDTO,
)
from inframeld_backend.access.application.dtos.project_action_target_dto import (
    ProjectActionTargetDTO,
)
from inframeld_backend.access.application.services.action_authorization_service import (
    ActionAuthorizationService,
)
from inframeld_backend.access.domain.enums.model_connection_action import ModelConnectionAction
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.readers.postgres_project_action_facts_reader import (
    PostgresProjectActionFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_scope_lock import (
    PostgresProjectScopeLock,
)
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.model_connection_action_grant_row import (
    ModelConnectionActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.model_connection_row import ModelConnectionRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.indexing.domain.enums.embedding_profile_action import EmbeddingProfileAction
from inframeld_backend.indexing.domain.enums.processing_profile_action import (
    ProcessingProfileAction,
)
from inframeld_backend.indexing.domain.value_objects.embedding_profile_id import EmbeddingProfileId
from inframeld_backend.indexing.domain.value_objects.processing_profile_id import (
    ProcessingProfileId,
)
from inframeld_backend.indexing.infrastructure.rows.embedding_profile_action_grant_row import (
    EmbeddingProfileActionGrantRow,
)
from inframeld_backend.indexing.infrastructure.rows.embedding_profile_row import EmbeddingProfileRow
from inframeld_backend.indexing.infrastructure.rows.processing_profile_action_grant_row import (
    ProcessingProfileActionGrantRow,
)
from inframeld_backend.indexing.infrastructure.rows.processing_profile_row import (
    ProcessingProfileRow,
)
from inframeld_backend.knowledge.application.value_objects.collection_id import CollectionId
from inframeld_backend.knowledge.infrastructure.rows.collection_action_grant_row import (
    CollectionActionGrantRow,
)
from inframeld_backend.knowledge.infrastructure.rows.collection_row import CollectionRow
from inframeld_backend.pipelines.application.dtos.pipeline_creation_dto import PipelineCreationDTO
from inframeld_backend.pipelines.application.dtos.saved_pipeline_dto import SavedPipelineDTO
from inframeld_backend.pipelines.application.value_objects.pipeline_configuration import (
    PipelineConfiguration,
)
from inframeld_backend.pipelines.domain.enums.pipeline_action import PipelineAction
from inframeld_backend.pipelines.domain.enums.pipeline_reranker import PipelineReranker
from inframeld_backend.pipelines.domain.value_objects.pipeline_id import PipelineId
from inframeld_backend.pipelines.infrastructure.rows.pipeline_action_grant_row import (
    PipelineActionGrantRow,
)
from inframeld_backend.pipelines.infrastructure.rows.pipeline_configuration_revision_row import (
    PipelineConfigurationRevisionRow,
)
from inframeld_backend.pipelines.infrastructure.rows.pipeline_creation_result_row import (
    PipelineCreationResultRow,
)
from inframeld_backend.pipelines.infrastructure.rows.pipeline_row import PipelineRow
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.dtos.generation_model_settings_dto import (
    GenerationModelSettingsDTO,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.model_role import ModelRole
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    DependencyUnavailableError,
    ResourceNotFoundError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)

_CREATE = ActionId(ProjectAction.CREATE_PIPELINES.value)
_INITIAL_ACTIONS = tuple(PipelineAction)


class PostgresPipelineRepository:
    """Persist exact Pipeline settings and original creation in the caller's transaction."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        application_key_profile: ApplicationKeyVerificationProfileDTO | None = None,
    ) -> None:
        self._session = session
        self._facts = PostgresProjectActionFactsReader(
            session, application_key_profile=application_key_profile
        )

    async def create(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        name: ResourceName,
        display_name: SubmittedDisplayName,
        configuration: PipelineConfiguration,
        operation_id: OperationId,
    ) -> PipelineCreationDTO:
        """Consume a real creation reservation and leave finalization to its owner."""
        if isinstance(access.authentication_evidence, ApplicationKeyAuthenticationDTO):
            raise AccessDeniedError()

        scope = await self._lock_scope(access, project_id)
        facts = await self._facts.read_action_facts(
            access=access, action_id=_CREATE, target=ProjectActionTargetDTO(project_id)
        )
        if facts is None:
            raise ResourceNotFoundError()
        ActionAuthorizationService.require_authorization_from_facts(access=access, facts=facts)

        principal = access.actor_principal_id
        reservation = await self._session.scalar(
            select(IdempotencyReservationRow)
            .where(
                IdempotencyReservationRow.operation_id == operation_id.value,
                IdempotencyReservationRow.organization_id == scope.organization_id.value,
                IdempotencyReservationRow.project_id == project_id.value,
                IdempotencyReservationRow.principal_id == principal.value,
                IdempotencyReservationRow.method == HttpMethod.POST.value,
                IdempotencyReservationRow.requested_route
                == f"/internal/projects/{project_id.value}/pipelines",
                IdempotencyReservationRow.lookup_authority_family
                == OperationLookupAuthorityFamily.PROJECT_ACTION_USE.value,
                IdempotencyReservationRow.lookup_action_id == _CREATE.value,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if reservation is None:
            raise ConflictError("The original Pipeline creation reservation is unavailable.")

        original = await self._session.get(PipelineCreationResultRow, operation_id.value)
        if original is not None:
            if (
                reservation.state is not OperationReservationState.REPLAYABLE
                or reservation.replay_kind is not OperationReplayKind.SAFE_RESULT
                or reservation.expires_at is None
                or not await self._session.scalar(
                    select(func.clock_timestamp() < reservation.expires_at)
                )
            ):
                raise ConflictError("The original Pipeline creation result is unavailable.")

            result = await self._read_original(scope, principal, original)
            if (
                result.pipeline.name != name
                or result.pipeline.display_name != display_name
                or result.pipeline.configuration != configuration
            ):
                raise ConflictError(
                    "The supplied Pipeline configuration differs from the original."
                )
            return result

        if (
            reservation.state is not OperationReservationState.IN_PROGRESS
            or reservation.replay_kind is not None
            or reservation.expires_at is not None
        ):
            raise ConflictError("The original Pipeline creation result is unavailable.")

        await self._require_configuration_access(
            scope, principal, facts.principal.kind, configuration
        )

        if await self._session.scalar(
            select(
                exists().where(
                    PipelineRow.project_id == project_id.value, PipelineRow.name == name.value
                )
            )
        ):
            raise ConflictError("This Project already has a Pipeline with that name.")
        project = await self._session.get(ProjectRow, project_id.value, populate_existing=True)
        if project is None:
            raise ResourceNotFoundError()
        before = project.access_revision
        RevisionValidation.require(before)
        if before == RevisionValidation.MAX_VALUE:
            raise ConflictError("The Project access revision cannot advance.")

        pipeline = PipelineRow(
            id=uuid4(),
            installation_id=scope.installation_id.value,
            organization_id=scope.organization_id.value,
            project_id=project_id.value,
            name=name.value,
            display_name=display_name.value,
            current_revision=1,
        )
        self._session.add(pipeline)
        await self._session.flush()
        saved = PipelineConfigurationRevisionRow(
            pipeline_id=pipeline.id,
            revision=pipeline.current_revision,
            installation_id=pipeline.installation_id,
            organization_id=pipeline.organization_id,
            project_id=pipeline.project_id,
            collection_id=configuration.collection_id.value,
            processing_profile_id=configuration.processing_profile_id.value,
            embedding_profile_id=configuration.embedding_profile_id.value,
            model_connection_id=configuration.model_connection_id.value,
            model_alias=configuration.model_alias,
            prompt=configuration.prompt,
            reranker=configuration.reranker.value,
            top_k=configuration.top_k,
            max_passages=configuration.max_passages,
            output_tokens=configuration.generation.output_tokens,
            created_by_principal_id=principal.value,
        )
        self._session.add(saved)
        await self._session.flush()
        self._session.add_all(
            [
                PipelineActionGrantRow(
                    project_id=project_id.value,
                    pipeline_id=pipeline.id,
                    recipient_principal_id=principal.value,
                    action=action.value,
                    recipient_kind=PrincipalKind.HUMAN,
                    can_grant=True,
                    assigned_by_principal_id=principal.value,
                )
                for action in _INITIAL_ACTIONS
            ]
        )
        project.access_revision = before + 1
        result_row = PipelineCreationResultRow(
            operation_id=operation_id.value,
            installation_id=pipeline.installation_id,
            organization_id=pipeline.organization_id,
            project_id=pipeline.project_id,
            creator_principal_id=principal.value,
            pipeline_id=pipeline.id,
            configuration_revision=saved.revision,
            before_revision=before,
            project_access_revision=project.access_revision,
            initial_actions=[action.value for action in _INITIAL_ACTIONS],
            can_grant=True,
            name=name.value,
            display_name=display_name.value,
        )
        self._session.add_all(
            [
                result_row,
                AccessAuditEventRow(
                    id=uuid4(),
                    organization_id=pipeline.organization_id,
                    actor_kind=PrincipalKind.HUMAN.value,
                    event_type="pipeline_created",
                    target_kind="pipeline",
                    target_id=pipeline.id,
                    project_id=project_id.value,
                    actor_principal_id=principal.value,
                    after_values={
                        "configuration_revision": saved.revision,
                        "project_access_revision": project.access_revision,
                        "initial_actions": result_row.initial_actions,
                    },
                    correlation_id=operation_id.value,
                ),
            ]
        )
        await self._session.flush()
        return PipelineCreationDTO(
            pipeline=SavedPipelineDTO(
                installation_id=scope.installation_id,
                organization_id=scope.organization_id,
                project_id=project_id,
                pipeline_id=PipelineId(pipeline.id),
                revision=saved.revision,
                name=name,
                display_name=display_name,
                configuration=configuration,
            ),
            operation_id=operation_id,
            project_access_revision=result_row.project_access_revision,
            initial_actions=_INITIAL_ACTIONS,
        )

    async def require_build(
        self, *, access: AccessContextDTO, project_id: ProjectId, pipeline_id: PipelineId
    ) -> ArtifactScopeDTO:
        """Authorize the exact Build under the Project update turn without resolving inputs."""
        scope = await self._lock_scope(access, project_id)
        facts = await self._facts.read_scope_facts(
            access=access, target=ProjectActionTargetDTO(project_id)
        )
        if facts is None:
            raise ResourceNotFoundError()
        exact_grant = await self._session.scalar(
            select(
                exists().where(
                    PipelineActionGrantRow.project_id == project_id.value,
                    PipelineActionGrantRow.pipeline_id == pipeline_id.value,
                    PipelineActionGrantRow.recipient_principal_id
                    == access.actor_principal_id.value,
                    PipelineActionGrantRow.recipient_kind == facts.principal.kind,
                    PipelineActionGrantRow.action == PipelineAction.BUILD.value,
                )
            )
            .select_from(PipelineRow)
            .where(
                PipelineRow.installation_id == scope.installation_id.value,
                PipelineRow.organization_id == scope.organization_id.value,
                PipelineRow.project_id == project_id.value,
                PipelineRow.id == pipeline_id.value,
            )
        )
        if exact_grant is None:
            raise ResourceNotFoundError()
        ActionAuthorizationService.require_authorization_from_facts(
            access=access, facts=replace(facts, has_exact_action_grant=exact_grant)
        )
        return scope

    async def load_for_build(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        pipeline_id: PipelineId,
        expected_revision: int,
    ) -> SavedPipelineDTO:
        """Capture currently reviewed settings after original-operation recovery."""
        scope = await self.require_build(
            access=access, project_id=project_id, pipeline_id=pipeline_id
        )
        actor = access.actor_principal_id
        kind = (
            PrincipalKind.APPLICATION
            if isinstance(access.authentication_evidence, ApplicationKeyAuthenticationDTO)
            else PrincipalKind.HUMAN
        )
        rows = (
            (
                await self._session.execute(
                    select(PipelineRow, PipelineConfigurationRevisionRow)
                    .join(
                        PipelineConfigurationRevisionRow,
                        (PipelineConfigurationRevisionRow.pipeline_id == PipelineRow.id)
                        & (
                            PipelineConfigurationRevisionRow.revision
                            == PipelineRow.current_revision
                        ),
                    )
                    .where(
                        PipelineRow.id == pipeline_id.value,
                        PipelineRow.project_id == project_id.value,
                    )
                    .execution_options(populate_existing=True)
                )
            )
            .tuples()
            .one_or_none()
        )
        if rows is None:
            raise ResourceNotFoundError()
        pipeline, current = rows
        if type(expected_revision) is not int or current.revision != expected_revision:
            raise StaleRevisionError()
        saved = self._restore_configuration(
            current, name=pipeline.name, display_name=pipeline.display_name
        )
        await self._require_configuration_access(scope, actor, kind, saved.configuration)
        return saved

    async def _lock_scope(
        self, access: AccessContextDTO, project_id: ProjectId
    ) -> ArtifactScopeDTO:
        organization_id = await PostgresProjectScopeLock.acquire(
            self._session, access.actor_principal_id, project_id, shared=False
        )
        if organization_id is None:
            raise ResourceNotFoundError()
        installation_id = await self._session.scalar(
            select(InstallationIdentityRow.installation_id).where(
                InstallationIdentityRow.singleton_key == 1
            )
        )
        if installation_id is None:
            raise DependencyUnavailableError("The installation identity is not available.")
        return ArtifactScopeDTO(
            InstallationId(installation_id), OrganizationId(organization_id), project_id
        )

    async def _read_original(
        self, scope: ArtifactScopeDTO, principal: PrincipalId, original: PipelineCreationResultRow
    ) -> PipelineCreationDTO:
        if (
            original.installation_id != scope.installation_id.value
            or original.organization_id != scope.organization_id.value
            or original.project_id != scope.project_id.value
            or original.creator_principal_id != principal.value
            or original.project_access_revision != original.before_revision + 1
            or original.initial_actions != [action.value for action in _INITIAL_ACTIONS]
            or original.can_grant is not True
        ):
            raise ConflictError("The original Pipeline creation record is inconsistent.")
        saved = await self._session.get(
            PipelineConfigurationRevisionRow,
            (original.pipeline_id, original.configuration_revision),
        )
        if saved is None:
            raise ConflictError("The original Pipeline configuration is unavailable.")
        return PipelineCreationDTO(
            pipeline=self._restore_configuration(
                saved, name=original.name, display_name=original.display_name
            ),
            operation_id=OperationId(original.operation_id),
            project_access_revision=original.project_access_revision,
            initial_actions=_INITIAL_ACTIONS,
        )

    @staticmethod
    def _restore_configuration(
        saved: PipelineConfigurationRevisionRow, *, name: str, display_name: str
    ) -> SavedPipelineDTO:
        return SavedPipelineDTO(
            installation_id=InstallationId(saved.installation_id),
            organization_id=OrganizationId(saved.organization_id),
            project_id=ProjectId(saved.project_id),
            pipeline_id=PipelineId(saved.pipeline_id),
            revision=saved.revision,
            name=ResourceName(name),
            display_name=SubmittedDisplayName(display_name),
            configuration=PipelineConfiguration(
                collection_id=CollectionId(saved.collection_id),
                processing_profile_id=ProcessingProfileId(saved.processing_profile_id),
                embedding_profile_id=EmbeddingProfileId(saved.embedding_profile_id),
                model_connection_id=ModelConnectionId(saved.model_connection_id),
                model_alias=saved.model_alias,
                prompt=saved.prompt,
                reranker=PipelineReranker(saved.reranker),
                top_k=saved.top_k,
                max_passages=saved.max_passages,
                generation=GenerationModelSettingsDTO(
                    saved.output_tokens, None, False, role=ModelRole.GENERATION
                ),
            ),
        )

    async def _require_configuration_access(
        self,
        scope: ArtifactScopeDTO,
        actor: PrincipalId,
        kind: PrincipalKind,
        configuration: PipelineConfiguration,
    ) -> None:
        project_id = scope.project_id.value
        org_id = scope.organization_id.value
        grants = await self._session.execute(
            select(
                exists().where(
                    CollectionActionGrantRow.project_id == project_id,
                    CollectionActionGrantRow.collection_id == configuration.collection_id.value,
                    CollectionActionGrantRow.recipient_principal_id == actor.value,
                    CollectionActionGrantRow.recipient_kind == kind,
                    CollectionActionGrantRow.action == "view-collection",
                ),
                exists().where(
                    ProcessingProfileActionGrantRow.project_id == project_id,
                    ProcessingProfileActionGrantRow.processing_profile_id
                    == configuration.processing_profile_id.value,
                    ProcessingProfileActionGrantRow.recipient_principal_id == actor.value,
                    ProcessingProfileActionGrantRow.recipient_kind == kind,
                    ProcessingProfileActionGrantRow.action == ProcessingProfileAction.USE.value,
                ),
                exists().where(
                    EmbeddingProfileActionGrantRow.project_id == project_id,
                    EmbeddingProfileActionGrantRow.embedding_profile_id
                    == configuration.embedding_profile_id.value,
                    EmbeddingProfileActionGrantRow.recipient_principal_id == actor.value,
                    EmbeddingProfileActionGrantRow.recipient_kind == kind,
                    EmbeddingProfileActionGrantRow.action == EmbeddingProfileAction.USE.value,
                ),
                exists().where(
                    ModelConnectionActionGrantRow.project_id == project_id,
                    ModelConnectionActionGrantRow.model_connection_id
                    == configuration.model_connection_id.value,
                    ModelConnectionActionGrantRow.recipient_principal_id == actor.value,
                    ModelConnectionActionGrantRow.recipient_kind == kind,
                    ModelConnectionActionGrantRow.action == ModelConnectionAction.USE.value,
                ),
            )
            .select_from(CollectionRow)
            .join(ProcessingProfileRow, ProcessingProfileRow.project_id == CollectionRow.project_id)
            .join(EmbeddingProfileRow, EmbeddingProfileRow.project_id == CollectionRow.project_id)
            .join(ModelConnectionRow, ModelConnectionRow.project_id == CollectionRow.project_id)
            .where(
                CollectionRow.id == configuration.collection_id.value,
                CollectionRow.installation_id == scope.installation_id.value,
                CollectionRow.organization_id == org_id,
                CollectionRow.project_id == project_id,
                ProcessingProfileRow.id == configuration.processing_profile_id.value,
                ProcessingProfileRow.organization_id == org_id,
                EmbeddingProfileRow.id == configuration.embedding_profile_id.value,
                EmbeddingProfileRow.organization_id == org_id,
                ModelConnectionRow.id == configuration.model_connection_id.value,
                ModelConnectionRow.organization_id == org_id,
                ModelConnectionRow.retired_at.is_(None),
            )
        )
        current = grants.tuples().one_or_none()
        if current is None:
            raise ResourceNotFoundError()
        if not all(current):
            raise AccessDeniedError()
