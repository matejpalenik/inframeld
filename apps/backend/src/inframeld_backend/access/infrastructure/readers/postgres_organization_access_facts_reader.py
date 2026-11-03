import asyncio
from typing import override

from sqlalchemy import BigInteger, Nullable, String, and_, func, literal, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_facts_dto import (
    HumanOAuthCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.organization_access_facts_dto import (
    OrganizationAccessFactsDTO,
)
from inframeld_backend.access.application.dtos.organization_action_grant_dto import (
    OrganizationActionGrantDTO,
)
from inframeld_backend.access.application.protocols.organization_access_facts_reader import (
    OrganizationAccessFactsReader,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.value_objects.action_id import ActionId
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
from inframeld_backend.access.infrastructure.rows.organization_action_grant_row import (
    OrganizationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)

_SUPPORTED_ACTIONS = ("admit-users", "suspend-users", "restore-users", "create-projects")


class PostgresOrganizationAccessFactsReader(OrganizationAccessFactsReader):
    """Observe caller-only assignments coherently, with ordered locks for creation."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def read(self, *, access: AccessContextDTO) -> OrganizationAccessFactsDTO | None:
        pending = (
            select(IdentityRecoveryAdmissionRow.operation_id)
            .join(
                HumanIdentityLinkRow,
                and_(
                    HumanIdentityLinkRow.authority == IdentityRecoveryAdmissionRow.authority,
                    HumanIdentityLinkRow.subject == IdentityRecoveryAdmissionRow.subject,
                ),
            )
            .where(
                HumanIdentityLinkRow.principal_id == PrincipalRow.id,
                IdentityRecoveryAdmissionRow.installation_id
                == InstallationIdentityRow.installation_id,
                IdentityRecoveryAdmissionRow.released_at.is_(None),
            )
            .exists()
            .correlate(PrincipalRow, InstallationIdentityRow)
        )
        evidence = access.authentication_evidence
        binding_matches = (
            HumanCredentialStateQueries.binding_matches_actor(evidence)
            if isinstance(evidence, HumanOAuthCredentialBindingDTO)
            else literal(False)
        )
        version = (
            Nullable(HumanCredentialStateQueries.version_for_actor(evidence))
            if isinstance(evidence, HumanOAuthCredentialBindingDTO)
            else Nullable(literal(None, BigInteger))
        )
        statement = (
            select(
                PrincipalRow,
                OrganizationRow.access_revision,
                Nullable(OrganizationActionGrantRow.action),
                Nullable(OrganizationActionGrantRow.can_grant),
                pending,
                binding_matches,
                version,
                Nullable(InstallationIdentityRow.installation_id),
            )
            .select_from(PrincipalRow)
            .join(OrganizationRow, OrganizationRow.id == PrincipalRow.organization_id)
            .outerjoin(InstallationIdentityRow, InstallationIdentityRow.singleton_key == 1)
            .outerjoin(
                OrganizationActionGrantRow,
                and_(
                    OrganizationActionGrantRow.organization_id == PrincipalRow.organization_id,
                    OrganizationActionGrantRow.recipient_principal_id == PrincipalRow.id,
                    OrganizationActionGrantRow.recipient_kind == PrincipalRow.kind,
                    OrganizationActionGrantRow.action.in_(_SUPPORTED_ACTIONS),
                ),
            )
            .where(PrincipalRow.id == access.actor_principal_id.value)
            .order_by(OrganizationActionGrantRow.action)
            .execution_options(populate_existing=True, autoflush=False)
        )
        try:
            async with asyncio.timeout(5):
                rows = (await self._session.execute(statement)).tuples().all()
        except (TimeoutError, OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None
        if not rows:
            return None
        principal, revision, _, _, blocked, matches, current_version, installed = rows[0]
        if installed is None:
            raise DependencyUnavailableError()
        grants: list[OrganizationActionGrantDTO] = []
        for (
            actor,
            observed_revision,
            action,
            delegation,
            recovering,
            linked,
            generation,
            identity,
        ) in rows:
            if (actor.id, observed_revision, recovering, linked, generation, identity) != (
                principal.id,
                revision,
                blocked,
                matches,
                current_version,
                installed,
            ):
                raise RuntimeError("Organization facts changed scope within one observation.")
            if action is not None:
                if delegation is None:
                    raise RuntimeError("The stored Organization assignment has no level.")
                grants.append(OrganizationActionGrantDTO(ActionId(action), delegation))
            elif delegation is not None:
                raise RuntimeError("The stored Organization assignment has no action.")
        return OrganizationAccessFactsDTO(
            Principal(
                PrincipalId(principal.id),
                OrganizationId(principal.organization_id),
                principal.kind,
                principal.status,
            ),
            revision,
            tuple(grants),
            blocked,
            HumanOAuthCredentialFactsDTO(
                matches,
                HumanCredentialVersion(current_version) if current_version is not None else None,
            )
            if isinstance(evidence, HumanOAuthCredentialBindingDTO)
            else None,
        )

    @override
    async def read_for_creation(
        self, *, access: AccessContextDTO, organization_id: OrganizationId
    ) -> OrganizationAccessFactsDTO | None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Creation facts require the active caller transaction.")
        try:
            async with asyncio.timeout(5):
                with self._session.no_autoflush:
                    isolation = await self._session.scalar(
                        select(func.current_setting("transaction_isolation", type_=String()))
                    )
                    if isolation != "read committed":
                        raise RuntimeError(
                            "Creation coordination requires READ COMMITTED isolation."
                        )
                    current = await self._session.scalar(
                        select(PrincipalRow.organization_id).where(
                            PrincipalRow.id == access.actor_principal_id.value
                        )
                    )
                    if current != organization_id.value:
                        return None
                    locked = await self._session.scalar(
                        select(OrganizationRow.id)
                        .where(OrganizationRow.id == organization_id.value)
                        .with_for_update(read=True)
                    )
                    if locked is None:
                        return None
                    # A separate statement after the wait observes current authority.
                    return await self.read(access=access)
        except TimeoutError:
            raise DependencyUnavailableError() from None
