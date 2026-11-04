import asyncio
from typing import override

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.human_admission_facts_dto import (
    HumanAdmissionFactsDTO,
)
from inframeld_backend.access.application.dtos.organization_access_facts_dto import (
    OrganizationAccessFactsDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.human_admission_facts_reader import (
    HumanAdmissionFactsReader,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.infrastructure.mappers.postgres_human_credential_state_mapper import (
    PostgresHumanCredentialStateMapper,
)
from inframeld_backend.access.infrastructure.readers.human_credential_state_queries import (
    HumanCredentialStateQueries,
)
from inframeld_backend.access.infrastructure.readers.postgres_organization_access_facts_reader import (
    PostgresOrganizationAccessFactsReader,
)
from inframeld_backend.access.infrastructure.resources.postgres_identity_coordinator import (
    PostgresIdentityCoordinator,
)
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class PostgresHumanAdmissionFactsReader(HumanAdmissionFactsReader):
    """Reread admission facts after the exact identity and exclusive Org turns."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def read_authorization(
        self,
        *,
        access: AccessContextDTO,
        organization_id: OrganizationId,
    ) -> OrganizationAccessFactsDTO | None:
        self._require_transaction()
        facts = await PostgresOrganizationAccessFactsReader(self._session).read(access=access)
        if facts is None or facts.principal.organization_id != organization_id:
            return None
        return facts

    @override
    async def read_for_admission(
        self,
        *,
        access: AccessContextDTO,
        organization_id: OrganizationId,
        identity: VerifiedHumanIdentityDTO,
    ) -> HumanAdmissionFactsDTO | None:
        self._require_transaction()
        try:
            async with asyncio.timeout(5):
                with self._session.no_autoflush:
                    installed = await self._session.scalar(
                        select(InstallationIdentityRow.installation_id).where(
                            InstallationIdentityRow.singleton_key == 1
                        )
                    )
                    if installed is None:
                        raise DependencyUnavailableError()
                    installation_id = InstallationId(installed)
                    await PostgresIdentityCoordinator(self._session).acquire(
                        installation_id=installation_id,
                        identity=identity,
                    )
                    locked = await self._session.scalar(
                        select(OrganizationRow.id)
                        .where(OrganizationRow.id == organization_id.value)
                        .with_for_update()
                    )
                    if locked is None:
                        return None

                    # Each decision observation starts after both coordination waits.
                    actor = await self.read_authorization(
                        access=access, organization_id=organization_id
                    )
                    if actor is None:
                        return None
                    link = await self._session.scalar(
                        select(HumanIdentityLinkRow)
                        .where(
                            HumanIdentityLinkRow.authority == identity.authority.value,
                            HumanIdentityLinkRow.subject == identity.subject.value,
                        )
                        .execution_options(populate_existing=True, autoflush=False)
                    )
                    principal = None
                    if link is not None:
                        row = await self._session.scalar(
                            select(PrincipalRow)
                            .where(
                                PrincipalRow.id == link.principal_id,
                                PrincipalRow.organization_id == link.organization_id,
                                PrincipalRow.kind == link.principal_kind,
                            )
                            .execution_options(populate_existing=True, autoflush=False)
                        )
                        if row is None:
                            raise RuntimeError(
                                "The current identity link has no coherent principal."
                            )
                        # Return inactive or foreign-Org state for the owning policy.
                        principal = Principal(
                            PrincipalId(row.id),
                            OrganizationId(row.organization_id),
                            row.kind,
                            row.status,
                        )
                    state_row = (
                        (
                            await self._session.execute(
                                HumanCredentialStateQueries.for_identity(identity)
                            )
                        )
                        .tuples()
                        .one_or_none()
                    )
                    state = PostgresHumanCredentialStateMapper.to_state(identity, state_row)
                    if state.installation_id != installation_id or state_row is None:
                        raise DependencyUnavailableError()
                    return HumanAdmissionFactsDTO(
                        installation_id, identity, actor, principal, state, state_row[3]
                    )
        except (TimeoutError, OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None

    def _require_transaction(self) -> None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Admission facts require the active caller transaction.")
