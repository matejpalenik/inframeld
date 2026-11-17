from typing import override

from sqlalchemy import and_, exists, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_key_authentication_dto import (
    ApplicationKeyAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.application_key_verification_profile_dto import (
    ApplicationKeyVerificationProfileDTO,
)
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.dtos.project_action_target_dto import (
    ProjectActionTargetDTO,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.readers.postgres_project_action_facts_reader import (
    PostgresProjectActionFactsReader,
)
from inframeld_backend.indexing.application.dtos.embedding_profile_dto import EmbeddingProfileDTO
from inframeld_backend.indexing.application.protocols.embedding_profile_read_repository import (
    EmbeddingProfileReadRepository,
)
from inframeld_backend.indexing.domain.enums.embedding_profile_action import (
    EmbeddingProfileAction,
)
from inframeld_backend.indexing.domain.value_objects.embedding_profile_id import (
    EmbeddingProfileId,
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
from inframeld_backend.indexing.infrastructure.rows.embedding_profile_row import (
    EmbeddingProfileRow,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class PostgresEmbeddingProfileReadRepository(EmbeddingProfileReadRepository):
    def __init__(
        self,
        session: AsyncSession,
        application_key_profile: ApplicationKeyVerificationProfileDTO | None,
    ) -> None:
        self._session = session
        self._scope_reader = PostgresProjectActionFactsReader(
            session, application_key_profile=application_key_profile
        )

    @override
    async def lock_scope(
        self, access: AccessContextDTO, project_id: ProjectId
    ) -> tuple[InstallationId, ProjectActionFactsDTO] | None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Embedding Profile access requires an active transaction.")
        try:
            # Application-key scope already acquires its Organization, Project and key locks.
            if not isinstance(access.authentication_evidence, ApplicationKeyAuthenticationDTO):
                organization = await ProcessingProfileProjectLock.acquire(
                    self._session, access.actor_principal_id, project_id, shared=True
                )
                if organization is None:
                    return None

            facts = await self._scope_reader.read_scope_facts(
                access=access, target=ProjectActionTargetDTO(project_id)
            )
            if facts is None:
                return None
            installation = await self._session.scalar(
                select(InstallationIdentityRow.installation_id).where(
                    InstallationIdentityRow.singleton_key == 1
                )
            )
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None
        if installation is None:
            raise DependencyUnavailableError("The installation identity is unavailable.")
        return InstallationId(installation), facts

    @override
    async def get_visible(
        self, facts: ProjectActionFactsDTO, project_id: ProjectId, profile_id: EmbeddingProfileId
    ) -> EmbeddingProfileDTO | None:
        try:
            row = await self._session.scalar(
                select(EmbeddingProfileRow).where(
                    self.profile_visibility(facts, project_id),
                    EmbeddingProfileRow.id == profile_id.value,
                )
            )
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None

        return self._mapped(row) if row is not None else None

    @override
    async def list_visible(
        self,
        facts: ProjectActionFactsDTO,
        project_id: ProjectId,
        after: EmbeddingProfileId | None,
        limit: int,
    ) -> tuple[EmbeddingProfileDTO, ...]:
        query = select(EmbeddingProfileRow).where(self.profile_visibility(facts, project_id))
        if after is not None:
            query = query.where(EmbeddingProfileRow.id > after.value)
        try:
            rows = await self._session.scalars(query.order_by(EmbeddingProfileRow.id).limit(limit))
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None
        return tuple(self._mapped(row) for row in rows)

    @staticmethod
    def _mapped(row: EmbeddingProfileRow) -> EmbeddingProfileDTO:
        try:
            return PostgresEmbeddingProfileMapper.profile(row)
        except ValueError:
            raise DependencyUnavailableError(
                "The stored Embedding Profile is unavailable."
            ) from None

    @staticmethod
    def profile_visibility(
        facts: ProjectActionFactsDTO, project_id: ProjectId
    ) -> ColumnElement[bool]:
        """Restrict profile reads to the exact scope and recipient's current View grant."""
        profile = EmbeddingProfileRow
        grant = EmbeddingProfileActionGrantRow
        return and_(
            profile.project_id == project_id.value,
            profile.organization_id == facts.principal.organization_id.value,
            exists().where(
                grant.project_id == profile.project_id,
                grant.embedding_profile_id == profile.id,
                grant.recipient_principal_id == facts.principal.id.value,
                grant.recipient_kind == facts.principal.kind,
                grant.action == EmbeddingProfileAction.VIEW.value,
            ),
        )
