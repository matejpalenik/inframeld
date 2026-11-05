import asyncio
from typing import override

from sqlalchemy import BigInteger, Nullable, and_, literal, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.deletion_status_facts_dto import (
    DeletionStatusFactsDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_facts_dto import (
    HumanOAuthCredentialFactsDTO,
)
from inframeld_backend.access.application.protocols.deletion_status_facts_reader import (
    DeletionStatusFactsReader,
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
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_admission_row import (
    IdentityRecoveryAdmissionRow,
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


class PostgresDeletionStatusFactsReader(DeletionStatusFactsReader):
    """Coordinate current actor facts without requiring surviving Project relationships.

    Hold Organization coordination through the caller's projection transaction.
    The five-second deadline includes lock waits. The caller owns rollback.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def read(self, *, access: AccessContextDTO) -> DeletionStatusFactsDTO | None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Deletion status authorization requires a caller transaction.")
        try:
            async with asyncio.timeout(5):
                return await self._read_current(access)
        except (TimeoutError, OperationalError, SqlAlchemyTimeoutError, LookupError):
            raise DependencyUnavailableError() from None

    async def _read_current(self, access: AccessContextDTO) -> DeletionStatusFactsDTO | None:
        """Observe current deletion-lookup authority separately from retained operation results."""
        organization = await self._session.scalar(
            select(PrincipalRow.organization_id).where(
                PrincipalRow.id == access.actor_principal_id.value
            )
        )
        if organization is None:
            return None
        locked = await self._session.scalar(
            select(OrganizationRow.id)
            .where(OrganizationRow.id == organization)
            .with_for_update(read=True)
        )
        if locked is None:
            return None

        # Read eligibility and credential state afresh only after the lock wait.
        installed = await self._session.scalar(
            select(InstallationIdentityRow.installation_id).where(
                InstallationIdentityRow.singleton_key == 1
            )
        )
        if installed is None:
            raise DependencyUnavailableError("The installation identity is not available.")
        pending_recovery = (
            select(IdentityRecoveryAdmissionRow.operation_id)
            .join(
                HumanIdentityLinkRow,
                and_(
                    HumanIdentityLinkRow.authority == IdentityRecoveryAdmissionRow.authority,
                    HumanIdentityLinkRow.subject == IdentityRecoveryAdmissionRow.subject,
                ),
            )
            .where(
                IdentityRecoveryAdmissionRow.installation_id == installed,
                HumanIdentityLinkRow.principal_id == PrincipalRow.id,
                IdentityRecoveryAdmissionRow.released_at.is_(None),
            )
            .exists()
            .correlate(PrincipalRow)
        )
        evidence = access.authentication_evidence
        if isinstance(evidence, HumanOAuthCredentialBindingDTO):
            matches_actor = HumanCredentialStateQueries.binding_matches_actor(evidence)
            version = Nullable(HumanCredentialStateQueries.version_for_actor(evidence))
        else:
            matches_actor = literal(False)
            version = Nullable(literal(None, BigInteger))

        statement = (
            select(PrincipalRow, pending_recovery, matches_actor, version)
            .where(
                PrincipalRow.id == access.actor_principal_id.value,
                PrincipalRow.organization_id == locked,
            )
            .execution_options(populate_existing=True)
        )
        stored = (await self._session.execute(statement)).tuples().one_or_none()
        if stored is None:
            return None
        actor, pending, binding_matches, current_version = stored
        try:
            return DeletionStatusFactsDTO(
                installation_id=InstallationId(installed),
                principal=Principal(
                    PrincipalId(actor.id),
                    OrganizationId(actor.organization_id),
                    actor.kind,
                    actor.status,
                ),
                has_pending_recovery=pending,
                oauth_credential_facts=(
                    HumanOAuthCredentialFactsDTO(
                        binding_matches_actor=binding_matches,
                        current_version=HumanCredentialVersion(current_version)
                        if current_version is not None
                        else None,
                    )
                    if isinstance(evidence, HumanOAuthCredentialBindingDTO)
                    else None
                ),
            )
        except (TypeError, ValueError):
            raise DependencyUnavailableError() from None
