import asyncio
from typing import override

from sqlalchemy import BigInteger, Nullable, and_, exists, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.admitted_work_authority_dto import (
    AdmittedWorkAuthorityDTO,
)
from inframeld_backend.access.application.dtos.admitted_work_facts_dto import AdmittedWorkFactsDTO
from inframeld_backend.access.application.dtos.human_oauth_credential_facts_dto import (
    HumanOAuthCredentialFactsDTO,
)
from inframeld_backend.access.application.protocols.admitted_work_facts_reader import (
    AdmittedWorkFactsReader,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.infrastructure.readers.human_credential_state_queries import (
    HumanCredentialStateQueries,
)
from inframeld_backend.access.infrastructure.resources.postgres_identity_coordinator import (
    PostgresIdentityCoordinator,
)
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_admission_row import (
    IdentityRecoveryAdmissionRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class PostgresAdmittedWorkFactsReader(AdmittedWorkFactsReader):
    """Coordinate current job authority without reconstructing incoming authentication.

    Identity, organization and project locks remain held through the caller's
    commit. Provider waits must occur after this short session has closed.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def read(self, authority: AdmittedWorkAuthorityDTO) -> AdmittedWorkFactsDTO | None:
        if not self._session.in_transaction():
            raise RuntimeError("Admitted-work authorization requires its caller transaction.")
        try:
            async with asyncio.timeout(5):
                return await self._read(authority)
        except TimeoutError as error:
            raise DependencyUnavailableError(
                "Current job authority exceeded its database deadline."
            ) from error

    async def _read(self, authority: AdmittedWorkAuthorityDTO) -> AdmittedWorkFactsDTO | None:
        installation = await self._session.scalar(
            select(InstallationIdentityRow.installation_id).where(
                InstallationIdentityRow.singleton_key == 1
            )
        )
        if installation is None:
            raise DependencyUnavailableError("The installation identity is unavailable.")
        if installation != authority.installation_id.value:
            return None
        binding = authority.human_binding
        if binding is not None:
            await PostgresIdentityCoordinator(self._session).acquire(
                installation_id=authority.installation_id, identity=binding.identity
            )
        organization = await self._session.scalar(
            select(OrganizationRow.id)
            .where(OrganizationRow.id == authority.organization_id.value)
            .with_for_update(read=True)
        )
        if organization is None:
            return None
        project = await self._session.scalar(
            select(ProjectRow.id)
            .where(
                ProjectRow.id == authority.project_id.value,
                ProjectRow.organization_id == organization,
            )
            .with_for_update(read=True)
        )
        if project is None:
            return None

        member = exists().where(
            ProjectMembershipRow.project_id == ProjectRow.id,
            ProjectMembershipRow.principal_id == PrincipalRow.id,
        )
        granted = exists().where(
            ProjectActionGrantRow.project_id == ProjectRow.id,
            ProjectActionGrantRow.recipient_principal_id == PrincipalRow.id,
            ProjectActionGrantRow.action == authority.action_id.value,
        )
        recovery = (
            select(IdentityRecoveryAdmissionRow.operation_id)
            .join(
                HumanIdentityLinkRow,
                and_(
                    HumanIdentityLinkRow.authority == IdentityRecoveryAdmissionRow.authority,
                    HumanIdentityLinkRow.subject == IdentityRecoveryAdmissionRow.subject,
                ),
            )
            .where(
                IdentityRecoveryAdmissionRow.installation_id == installation,
                HumanIdentityLinkRow.principal_id == PrincipalRow.id,
                IdentityRecoveryAdmissionRow.released_at.is_(None),
            )
            .exists()
            .correlate(PrincipalRow)
        )
        matches = (
            HumanCredentialStateQueries.binding_matches_actor(binding)
            if binding is not None
            else literal(False)
        )
        version = (
            Nullable(HumanCredentialStateQueries.version_for_actor(binding))
            if binding is not None
            else Nullable(literal(None, BigInteger))
        )
        row = (
            (
                await self._session.execute(
                    select(
                        PrincipalRow, ProjectRow.status, member, granted, recovery, matches, version
                    )
                    .select_from(PrincipalRow)
                    .join(
                        ProjectRow,
                        and_(
                            ProjectRow.id == project,
                            ProjectRow.organization_id == PrincipalRow.organization_id,
                        ),
                    )
                    .where(
                        PrincipalRow.id == authority.principal_id.value,
                        PrincipalRow.organization_id == organization,
                    )
                    .execution_options(populate_existing=True)
                )
            )
            .tuples()
            .one_or_none()
        )
        if row is None:
            return None
        principal, status, is_member, has_grant, pending, binding_matches, current_version = row
        return AdmittedWorkFactsDTO(
            Principal(
                PrincipalId(principal.id),
                OrganizationId(principal.organization_id),
                principal.kind,
                principal.status,
            ),
            InstallationId(installation),
            status,
            is_member,
            has_grant,
            pending,
            HumanOAuthCredentialFactsDTO(
                binding_matches,
                HumanCredentialVersion(current_version) if current_version is not None else None,
            )
            if binding is not None
            else None,
        )
