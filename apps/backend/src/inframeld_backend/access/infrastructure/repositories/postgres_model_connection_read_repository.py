from typing import override

from sqlalchemy import Nullable, String, and_, exists, func, select
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
from inframeld_backend.access.application.dtos.model_connection_access_dto import (
    ModelConnectionAccessDTO,
)
from inframeld_backend.access.application.dtos.model_connection_dto import ModelConnectionDTO
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.dtos.project_action_target_dto import (
    ProjectActionTargetDTO,
)
from inframeld_backend.access.application.protocols.model_connection_read_repository import (
    ModelConnectionReadRepository,
)
from inframeld_backend.access.domain.enums.model_connection_action import ModelConnectionAction
from inframeld_backend.access.domain.enums.model_connection_authentication import (
    ModelConnectionAuthentication,
)
from inframeld_backend.access.domain.enums.model_connection_provider import ModelConnectionProvider
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.readers.postgres_project_action_facts_reader import (
    PostgresProjectActionFactsReader,
)
from inframeld_backend.access.infrastructure.rows.model_connection_action_grant_row import (
    ModelConnectionActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.model_connection_credential_row import (
    ModelConnectionCredentialRow,
)
from inframeld_backend.access.infrastructure.rows.model_connection_row import ModelConnectionRow
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class PostgresModelConnectionReadRepository(ModelConnectionReadRepository):
    """Read exact granted connections under the same turn as current credential checks."""

    def __init__(
        self,
        session: AsyncSession,
        application_key_profile: ApplicationKeyVerificationProfileDTO | None,
    ) -> None:
        self._session = session
        self._scope_reader = PostgresProjectActionFactsReader(
            session,
            application_key_profile=application_key_profile,
        )

    @override
    async def lock_scope(
        self, access: AccessContextDTO, project_id: ProjectId
    ) -> tuple[InstallationId, ProjectActionFactsDTO] | None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError(
                "Model connection observation requires an active caller transaction."
            )
        try:
            # Application-key scope already takes the organization, Project, and key locks.
            if not isinstance(access.authentication_evidence, ApplicationKeyAuthenticationDTO):
                if (
                    await self._session.scalar(
                        select(func.current_setting("transaction_isolation", type_=String()))
                    )
                    != "read committed"
                ):
                    raise RuntimeError(
                        "Model connection observation requires READ COMMITTED isolation."
                    )
                organization = await self._session.scalar(
                    select(PrincipalRow.organization_id).where(
                        PrincipalRow.id == access.actor_principal_id.value
                    )
                )
                if (
                    organization is None
                    or await self._session.scalar(
                        select(OrganizationRow.id)
                        .where(OrganizationRow.id == organization)
                        .with_for_update(read=True)
                    )
                    is None
                ):
                    return None
                if (
                    await self._session.scalar(
                        select(ProjectRow.id)
                        .where(
                            ProjectRow.id == project_id.value,
                            ProjectRow.organization_id == organization,
                        )
                        .with_for_update(read=True)
                    )
                    is None
                ):
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
            if installation is None:
                raise DependencyUnavailableError("The installation identity is unavailable.")
            return InstallationId(installation), facts
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None

    @override
    async def get_visible(
        self, facts: ProjectActionFactsDTO, project_id: ProjectId, connection_id: ModelConnectionId
    ) -> ModelConnectionDTO | None:
        try:
            result = await self._session.execute(
                self._visible(facts, project_id).where(ModelConnectionRow.id == connection_id.value)
            )
            row = result.tuples().one_or_none()
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None
        return self._metadata(*row) if row is not None else None

    @override
    async def list_visible(
        self,
        facts: ProjectActionFactsDTO,
        project_id: ProjectId,
        after: ModelConnectionId | None,
        limit: int,
    ) -> tuple[ModelConnectionDTO, ...]:
        query = self._visible(facts, project_id)
        if after is not None:
            query = query.where(ModelConnectionRow.id > after.value)
        try:
            result = await self._session.execute(query.order_by(ModelConnectionRow.id).limit(limit))
            rows = result.tuples().all()
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None
        return tuple(self._metadata(*row) for row in rows)

    @staticmethod
    def _visible(
        facts: ProjectActionFactsDTO, project_id: ProjectId
    ) -> Select[tuple[ModelConnectionRow, int | None, bool]]:
        slot = ModelConnectionCredentialRow
        return (
            select(ModelConnectionRow, Nullable(slot.revision), slot.key_id.is_not(None))
            .outerjoin(
                slot,
                and_(
                    slot.model_connection_id == ModelConnectionRow.id,
                    slot.project_id == ModelConnectionRow.project_id,
                    slot.organization_id == ModelConnectionRow.organization_id,
                ),
            )
            .where(
                ModelConnectionRow.project_id == project_id.value,
                ModelConnectionRow.organization_id == facts.principal.organization_id.value,
                ModelConnectionRow.retired_at.is_(None),
                exists().where(
                    ModelConnectionActionGrantRow.project_id == ModelConnectionRow.project_id,
                    ModelConnectionActionGrantRow.model_connection_id == ModelConnectionRow.id,
                    ModelConnectionActionGrantRow.recipient_principal_id
                    == facts.principal.id.value,
                    ModelConnectionActionGrantRow.recipient_kind == facts.principal.kind,
                    ModelConnectionActionGrantRow.action
                    == ModelConnectionAction.VIEW_CONFIGURATION.value,
                ),
            )
        )

    @staticmethod
    def _metadata(
        row: ModelConnectionRow, revision: int | None, present: bool
    ) -> ModelConnectionDTO:
        return ModelConnectionDTO(
            ProjectId(row.project_id),
            ModelConnectionId(row.id),
            ResourceName(row.name),
            row.display_name,
            ModelConnectionAccessDTO(
                ModelConnectionProvider(row.provider),
                row.base_url,
                row.api_version,
                ModelConnectionAuthentication(row.authentication),
            ),
            row.access_revision,
            credential_present=present,
            credential_revision=revision or 0,
        )
