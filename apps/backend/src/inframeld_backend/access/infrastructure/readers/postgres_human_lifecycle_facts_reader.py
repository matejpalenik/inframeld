from typing import override

from sqlalchemy import BigInteger, Nullable, and_, exists, literal, select
from sqlalchemy.exc import MultipleResultsFound, OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.browser_session_authentication_dto import (
    BrowserSessionAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.human_credential_facts_dto import (
    HumanCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.human_lifecycle_facts_dto import (
    HumanLifecycleFactsDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.human_lifecycle_facts_reader import (
    HumanLifecycleFactsReader,
)
from inframeld_backend.access.domain.entities.human_suspension import HumanSuspension
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.human_suspension_id import HumanSuspensionId
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.infrastructure.readers.human_credential_state_queries import (
    HumanCredentialStateQueries,
)
from inframeld_backend.access.infrastructure.resources.postgres_identity_coordinator import (
    PostgresIdentityCoordinator,
)
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
)
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.organization_action_grant_row import (
    OrganizationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.rows.human_suspension_obligation_row import (
    HumanSuspensionObligationRow,
)
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class PostgresHumanLifecycleFactsReader(HumanLifecycleFactsReader):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def read_authorization(
        self,
        *,
        access: AccessContextDTO,
        organization_id: OrganizationId,
        principal_id: PrincipalId,
        action_id: ActionId,
    ) -> HumanLifecycleFactsDTO | None:
        try:
            return await self._read(
                access, organization_id, principal_id, action_id, await self._installation()
            )
        except (OperationalError, SqlAlchemyTimeoutError, MultipleResultsFound) as error:
            raise DependencyUnavailableError() from error

    @override
    async def lock_for_change(
        self,
        *,
        access: AccessContextDTO,
        organization_id: OrganizationId,
        principal_id: PrincipalId,
        action_id: ActionId,
        identity: VerifiedHumanIdentityDTO,
    ) -> HumanLifecycleFactsDTO | None:
        try:
            installation = await self._installation()
            await PostgresIdentityCoordinator(self._session).acquire(
                installation_id=installation, identity=identity
            )
            locked = await self._session.scalar(
                select(OrganizationRow.id)
                .where(OrganizationRow.id == organization_id.value)
                .with_for_update()
            )
            if locked is None:
                return None
            return await self._read(access, organization_id, principal_id, action_id, installation)
        except (OperationalError, SqlAlchemyTimeoutError, MultipleResultsFound) as error:
            raise DependencyUnavailableError() from error

    async def _installation(self) -> InstallationId:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Human lifecycle facts require the active caller transaction.")
        installed = await self._session.scalar(
            select(InstallationIdentityRow.installation_id).where(
                InstallationIdentityRow.singleton_key == 1
            )
        )
        if installed is None:
            raise DependencyUnavailableError("The installation identity is unavailable.")
        return InstallationId(installed)

    async def _read(
        self,
        access: AccessContextDTO,
        organization_id: OrganizationId,
        principal_id: PrincipalId,
        action_id: ActionId,
        installation: InstallationId,
    ) -> HumanLifecycleFactsDTO | None:
        evidence = access.authentication_evidence
        human_evidence = isinstance(
            evidence, HumanOAuthCredentialBindingDTO | BrowserSessionAuthenticationDTO
        )
        if human_evidence:
            matches = HumanCredentialStateQueries.binding_matches_actor(evidence)
            version = Nullable(HumanCredentialStateQueries.version_for_actor(evidence))
        else:
            matches = literal(False)
            version = Nullable(literal(None, BigInteger))
        exact_grant = (
            exists()
            .where(
                OrganizationActionGrantRow.organization_id == organization_id.value,
                OrganizationActionGrantRow.recipient_principal_id == PrincipalRow.id,
                OrganizationActionGrantRow.recipient_kind == PrincipalRow.kind,
                OrganizationActionGrantRow.action == action_id.value,
            )
            .correlate(PrincipalRow)
        )
        actor = (
            (
                await self._session.execute(
                    select(
                        PrincipalRow,
                        OrganizationRow.access_revision,
                        exact_grant,
                        HumanCredentialStateQueries.pending_for_principal(
                            PrincipalRow.id, installation
                        ),
                        matches,
                        version,
                    )
                    .join(OrganizationRow, OrganizationRow.id == PrincipalRow.organization_id)
                    .where(
                        OrganizationRow.id == organization_id.value,
                        PrincipalRow.id == access.actor_principal_id.value,
                    )
                    .execution_options(populate_existing=True)
                )
            )
            .tuples()
            .one_or_none()
        )
        if actor is None:
            return None
        actor_row, revision, has_action, blocked, binding_matches, current_version = actor

        target = (
            (
                await self._session.execute(
                    select(
                        PrincipalRow,
                        Nullable(HumanIdentityLinkRow),
                        Nullable(HumanCredentialVersionRow.version),
                        HumanCredentialStateQueries.pending_for_principal(
                            PrincipalRow.id, installation
                        ),
                    )
                    .select_from(PrincipalRow)
                    .outerjoin(
                        HumanIdentityLinkRow,
                        and_(
                            HumanIdentityLinkRow.principal_id == PrincipalRow.id,
                            HumanIdentityLinkRow.organization_id == PrincipalRow.organization_id,
                            HumanIdentityLinkRow.principal_kind == PrincipalRow.kind,
                        ),
                    )
                    .outerjoin(
                        HumanCredentialVersionRow,
                        and_(
                            HumanCredentialVersionRow.installation_id == installation.value,
                            HumanCredentialVersionRow.authority == HumanIdentityLinkRow.authority,
                            HumanCredentialVersionRow.subject == HumanIdentityLinkRow.subject,
                        ),
                    )
                    .where(
                        PrincipalRow.id == principal_id.value,
                        PrincipalRow.organization_id == organization_id.value,
                    )
                    .execution_options(populate_existing=True)
                )
            )
            .tuples()
            .one_or_none()
        )
        target_row, link, target_version, recovery_block = (
            target if target is not None else (None, None, None, False)
        )
        identity = (
            VerifiedHumanIdentityDTO(
                IdentityAuthority(link.authority), IdentitySubject(link.subject)
            )
            if link is not None
            else None
        )
        original = await self._session.scalar(
            select(HumanSuspensionObligationRow)
            .where(
                HumanSuspensionObligationRow.installation_id == installation.value,
                HumanSuspensionObligationRow.organization_id == organization_id.value,
                HumanSuspensionObligationRow.principal_id == principal_id.value,
            )
            .order_by(HumanSuspensionObligationRow.access_revision.desc())
            .limit(1)
            .execution_options(populate_existing=True)
        )
        cleanup = (
            HumanSuspension(
                id=HumanSuspensionId(original.id),
                organization_id=organization_id,
                principal_id=principal_id,
                installation_id=installation,
                authority=IdentityAuthority(original.authority),
                subject=IdentitySubject(original.subject),
                kratos_sessions=original.kratos_sessions,
                hydra_cli_grants=original.hydra_cli_grants,
                hydra_remembered_logins=original.hydra_remembered_logins,
            )
            if original is not None
            else None
        )
        confirmed = (
            original.completed_at is not None
            and cleanup is not None
            and cleanup.is_cleanup_confirmed
            if original is not None
            else target_row is not None and target_row.status is PrincipalStatus.ACTIVE
        )
        return HumanLifecycleFactsDTO(
            installation_id=installation,
            organization_id=organization_id,
            access_revision=revision,
            action_id=action_id,
            actor=self._principal(actor_row),
            actor_has_pending_recovery=blocked,
            actor_credential_facts=HumanCredentialFactsDTO(
                binding_matches_actor=binding_matches,
                current_version=HumanCredentialVersion(current_version)
                if current_version is not None
                else None,
            )
            if human_evidence
            else None,
            actor_has_action=has_action,
            target=self._principal(target_row) if target_row is not None else None,
            target_identity=identity,
            target_version=HumanCredentialVersion(target_version)
            if target_version is not None
            else None,
            current_suspension=cleanup,
            required_cleanup_confirmed=confirmed,
            has_newer_recovery_block=recovery_block,
        )

    @staticmethod
    def _principal(row: PrincipalRow) -> Principal:
        return Principal(
            PrincipalId(row.id), OrganizationId(row.organization_id), row.kind, row.status
        )
