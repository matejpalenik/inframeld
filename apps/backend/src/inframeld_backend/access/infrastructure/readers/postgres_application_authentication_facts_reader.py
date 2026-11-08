import asyncio
from typing import override

from sqlalchemy import String, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_authentication_facts_dto import (
    ApplicationAuthenticationFactsDTO,
)
from inframeld_backend.access.application.dtos.application_key_authentication_dto import (
    ApplicationKeyAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.application_key_verification_profile_dto import (
    ApplicationKeyVerificationProfileDTO,
)
from inframeld_backend.access.application.protocols.application_authentication_facts_reader import (
    ApplicationAuthenticationFactsReader,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.mappers.postgres_application_key_facts_mapper import (
    PostgresApplicationKeyFactsMapper,
)
from inframeld_backend.access.infrastructure.readers.application_key_state_queries import (
    ApplicationKeyStateQueries,
)
from inframeld_backend.access.infrastructure.rows.application_account_row import (
    ApplicationAccountRow,
)
from inframeld_backend.access.infrastructure.rows.application_key_row import ApplicationKeyRow
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.infrastructure.resources.database import Database


class PostgresApplicationAuthenticationFactsReader(ApplicationAuthenticationFactsReader):
    """Observe current application admission through independent, bounded read sessions."""

    def __init__(self, database: Database) -> None:
        self._database = database

    @override
    async def read(self, principal_id: PrincipalId) -> ApplicationAuthenticationFactsDTO | None:
        try:
            async with asyncio.timeout(5.0), self._database.session() as session:
                observed = (
                    (await session.execute(ApplicationKeyStateQueries.local_account(principal_id)))
                    .tuples()
                    .one_or_none()
                )
                if observed is None:
                    return None
                principal, project_id, project_status, member, coherent = observed
                return ApplicationAuthenticationFactsDTO(
                    principal=Principal(
                        id=PrincipalId(principal.id),
                        organization_id=OrganizationId(principal.organization_id),
                        kind=principal.kind,
                        status=principal.status,
                    ),
                    project_id=ProjectId(project_id),
                    project_status=project_status,
                    is_project_member=member,
                    has_coherent_binding=coherent,
                )
        except (TimeoutError, OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None

    @override
    async def read_current(
        self, *, access: AccessContextDTO, profile: ApplicationKeyVerificationProfileDTO
    ) -> ApplicationAuthenticationFactsDTO | None:
        evidence = access.authentication_evidence
        if not isinstance(evidence, ApplicationKeyAuthenticationDTO):
            raise RuntimeError("Current application facts require application-key evidence.")

        try:
            async with asyncio.timeout(5.0), self._database.session() as session, session.begin():
                isolation = await session.scalar(
                    select(func.current_setting("transaction_isolation", type_=String()))
                )
                if isolation != "read committed":
                    raise RuntimeError(
                        "Current application facts require READ COMMITTED isolation."
                    )
                scope = (
                    (
                        await session.execute(
                            ApplicationKeyStateQueries.account_scope(access.actor_principal_id)
                        )
                    )
                    .tuples()
                    .one_or_none()
                )
                if scope is None:
                    return None
                observed_organization, observed_project = scope
                organization = await session.scalar(
                    select(OrganizationRow.id)
                    .where(OrganizationRow.id == observed_organization)
                    .with_for_update(read=True)
                )
                if organization is None:
                    return None
                project = await session.scalar(
                    select(ProjectRow.id)
                    .where(
                        ProjectRow.id == observed_project,
                        ProjectRow.organization_id == observed_organization,
                    )
                    .with_for_update(read=True)
                )
                if project is None:
                    return None
                organization_id, project_id = OrganizationId(organization), ProjectId(project)
                key_scope = ApplicationKeyStateQueries.key_scope(
                    key_id=evidence.key_id,
                    principal_id=access.actor_principal_id,
                    organization_id=organization_id,
                    project_id=project_id,
                )
                # FOR SHARE conflicts with an ordinary non-key revocation UPDATE.
                await session.scalar(
                    select(ApplicationKeyRow.key_id).where(key_scope).with_for_update(read=True)
                )

                local = (
                    (
                        await session.execute(
                            ApplicationKeyStateQueries.local_account(
                                access.actor_principal_id
                            ).where(
                                ApplicationAccountRow.organization_id == organization_id.value,
                                ApplicationAccountRow.project_id == project_id.value,
                            )
                        )
                    )
                    .tuples()
                    .one_or_none()
                )
                if local is None:
                    return None
                principal, current_project_id, project_status, member, coherent = local
                # Database UTC is observed only after coordination waits and local reads.
                key = (
                    (
                        await session.execute(
                            ApplicationKeyStateQueries.current_key(
                                key_id=evidence.key_id,
                                principal_id=access.actor_principal_id,
                                organization_id=organization_id,
                                project_id=project_id,
                                adapter=profile.adapter,
                            )
                        )
                    )
                    .tuples()
                    .one_or_none()
                )
                return ApplicationAuthenticationFactsDTO(
                    principal=Principal(
                        id=PrincipalId(principal.id),
                        organization_id=OrganizationId(principal.organization_id),
                        kind=principal.kind,
                        status=principal.status,
                    ),
                    project_id=ProjectId(current_project_id),
                    project_status=project_status,
                    is_project_member=member,
                    has_coherent_binding=coherent,
                    key_facts=PostgresApplicationKeyFactsMapper.to_facts(
                        key, evidence=evidence, profile=profile
                    ),
                )
        except (TimeoutError, OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None
