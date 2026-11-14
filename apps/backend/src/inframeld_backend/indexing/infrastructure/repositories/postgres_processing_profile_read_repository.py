from typing import override

from sqlalchemy import exists, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

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
from inframeld_backend.indexing.application.dtos.processing_profile_dto import ProcessingProfileDTO
from inframeld_backend.indexing.application.protocols.processing_profile_read_repository import (
    ProcessingProfileReadRepository,
)
from inframeld_backend.indexing.domain.enums.processing_profile_action import (
    ProcessingProfileAction,
)
from inframeld_backend.indexing.domain.value_objects.processing_profile_id import (
    ProcessingProfileId,
)
from inframeld_backend.indexing.infrastructure.mappers.postgres_processing_profile_mapper import (
    PostgresProcessingProfileMapper,
)
from inframeld_backend.indexing.infrastructure.readers.processing_profile_project_lock import (
    ProcessingProfileProjectLock,
)
from inframeld_backend.indexing.infrastructure.rows.processing_profile_action_grant_row import (
    ProcessingProfileActionGrantRow,
)
from inframeld_backend.indexing.infrastructure.rows.processing_profile_row import (
    ProcessingProfileRow,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class PostgresProcessingProfileReadRepository(ProcessingProfileReadRepository):
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
            raise RuntimeError("Processing Profile access requires an active transaction.")
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
        self, facts: ProjectActionFactsDTO, project_id: ProjectId, profile_id: ProcessingProfileId
    ) -> ProcessingProfileDTO | None:
        try:
            row = await self._session.scalar(
                self._visible(facts, project_id).where(ProcessingProfileRow.id == profile_id.value)
            )
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None
        return PostgresProcessingProfileMapper.profile(row) if row is not None else None

    @override
    async def list_visible(
        self,
        facts: ProjectActionFactsDTO,
        project_id: ProjectId,
        after: ProcessingProfileId | None,
        limit: int,
    ) -> tuple[ProcessingProfileDTO, ...]:
        query = self._visible(facts, project_id)
        if after is not None:
            query = query.where(ProcessingProfileRow.id > after.value)
        try:
            rows = await self._session.scalars(query.order_by(ProcessingProfileRow.id).limit(limit))
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None
        return tuple(PostgresProcessingProfileMapper.profile(row) for row in rows)

    @staticmethod
    def _visible(
        facts: ProjectActionFactsDTO, project_id: ProjectId
    ) -> Select[tuple[ProcessingProfileRow]]:
        profile = ProcessingProfileRow
        grant = ProcessingProfileActionGrantRow
        return select(profile).where(
            profile.project_id == project_id.value,
            profile.organization_id == facts.principal.organization_id.value,
            exists().where(
                grant.project_id == profile.project_id,
                grant.processing_profile_id == profile.id,
                grant.recipient_principal_id == facts.principal.id.value,
                grant.recipient_kind == facts.principal.kind,
                grant.action == ProcessingProfileAction.VIEW.value,
            ),
        )
