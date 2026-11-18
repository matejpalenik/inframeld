from typing import override

from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.resources.postgres_identity_coordinator import (
    PostgresIdentityCoordinator,
)
from inframeld_backend.knowledge.application.value_objects.collection_revision_id import (
    CollectionRevisionId,
)
from inframeld_backend.knowledge.infrastructure.repositories.postgres_collection_repository import (
    PostgresCollectionRepository,
)
from inframeld_backend.pipelines.application.protocols.pipeline_pdf_preparation_facts_reader import (
    PipelinePdfPreparationFactsReader,
)
from inframeld_backend.pipelines.application.value_objects.pipeline_pdf_preparation_input import (
    PipelinePdfPreparationInput,
)
from inframeld_backend.pipelines.domain.value_objects.pipeline_id import PipelineId
from inframeld_backend.pipelines.infrastructure.repositories.postgres_pipeline_repository import (
    PostgresPipelineRepository,
)
from inframeld_backend.releases.infrastructure.readers.postgres_deployment_association_reader import (
    PostgresDeploymentAssociationReader,
)
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    InvalidInputError,
)


class PostgresPipelinePdfPreparationFactsReader(PipelinePdfPreparationFactsReader):
    """Capture an authorized private preparation from the three owning resources."""

    def __init__(self, session: AsyncSession) -> None:
        self._identity = PostgresIdentityCoordinator(session)
        self._pipelines = PostgresPipelineRepository(session)
        self._collections = PostgresCollectionRepository(session)
        self._deployments = PostgresDeploymentAssociationReader(session)

    @override
    async def authorize(
        self, *, access: AccessContextDTO, project_id: ProjectId, pipeline_id: PipelineId
    ) -> ArtifactScopeDTO:
        evidence = access.authentication_evidence
        if not isinstance(evidence, HumanOAuthCredentialBindingDTO):
            raise AccessDeniedError()

        # Establish the human identity turn before acquiring either scoped write lock.
        await self._identity.acquire(
            installation_id=evidence.installation_id, identity=evidence.identity
        )
        return await self._pipelines.require_build(
            access=access, project_id=project_id, pipeline_id=pipeline_id
        )

    @override
    async def read_reviewed(
        self,
        *,
        access: AccessContextDTO,
        scope: ArtifactScopeDTO,
        pipeline_id: PipelineId,
        configuration_revision: int,
        collection_revision_id: CollectionRevisionId,
    ) -> PipelinePdfPreparationInput:
        saved = await self._pipelines.load_for_build(
            access=access,
            project_id=scope.project_id,
            pipeline_id=pipeline_id,
            expected_revision=configuration_revision,
        )
        await self._deployments.require_absent(scope=scope, pipeline_id=pipeline_id)
        selection = await self._collections.require_reviewed_sources(
            access=access,
            project_id=scope.project_id,
            collection_id=saved.configuration.collection_id,
            revision_id=collection_revision_id,
        )
        if len(selection) != 1:
            raise InvalidInputError("Private PDF preparation requires exactly one selected PDF.")
        return PipelinePdfPreparationInput(
            collection_id=saved.configuration.collection_id,
            collection_revision_id=collection_revision_id,
            configuration_revision=configuration_revision,
            processing_profile_id=saved.configuration.processing_profile_id,
            source=selection[0],
        )
