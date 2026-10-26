import asyncio
from typing import override

from sqlalchemy import Nullable, and_, exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from inframeld_backend.access.application.dtos.identity_recovery_admission_dto import (
    IdentityRecoveryAdmissionDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_completion_facts_dto import (
    IdentityRecoveryCompletionFactsDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_event_dto import (
    IdentityRecoveryEventDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.identity_recovery_completion_facts_reader import (
    IdentityRecoveryCompletionFactsReader,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_recovery_flow_id import (
    IdentityRecoveryFlowId,
)
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.infrastructure.resources.postgres_identity_coordinator import (
    PostgresIdentityCoordinator,
)
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
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
    ResourceNotFoundError,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)

_RECOVERY_COMPLETION_TIMEOUT_SECONDS = 5.0


class PostgresIdentityRecoveryCompletionFactsReader(IdentityRecoveryCompletionFactsReader):
    """Lock the original identity, then its organization before reading release facts.

    A five-second deadline includes lock waits. Refresh ORM observations even
    when this session previously loaded the same records.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def read(
        self,
        *,
        installation_id: InstallationId,
        authority: IdentityAuthority,
        flow_id: IdentityRecoveryFlowId,
    ) -> IdentityRecoveryCompletionFactsDTO:
        transaction = self._session.get_nested_transaction() or self._session.get_transaction()
        if transaction is None or not transaction.is_active:
            raise RuntimeError("Recovery completion requires an active caller transaction.")
        loop = asyncio.get_running_loop()
        deadline = loop.time() + _RECOVERY_COMPLETION_TIMEOUT_SECONDS
        try:
            async with asyncio.timeout_at(deadline):
                facts = await self._read(
                    installation_id=installation_id, authority=authority, flow_id=flow_id
                )
                if loop.time() >= deadline:
                    raise TimeoutError()
                return facts
        except TimeoutError as error:
            raise DependencyUnavailableError(
                "Recovery completion exceeded its database deadline."
            ) from error

    async def _read(
        self,
        *,
        installation_id: InstallationId,
        authority: IdentityAuthority,
        flow_id: IdentityRecoveryFlowId,
    ) -> IdentityRecoveryCompletionFactsDTO:
        installation_statement = select(InstallationIdentityRow.installation_id).where(
            InstallationIdentityRow.singleton_key == 1
        )
        current_installation = await self._session.scalar(
            installation_statement.execution_options(autoflush=False)
        )
        if current_installation != installation_id.value:
            raise DependencyUnavailableError("The installation identity is not available.")

        identity = await self._read_original_recovery_identity(
            installation_id=installation_id, authority=authority, flow_id=flow_id
        )
        await PostgresIdentityCoordinator(self._session).acquire(
            installation_id=installation_id, identity=identity
        )
        if await self._session.scalar(installation_statement) != installation_id.value:
            raise DependencyUnavailableError("The installation identity is not available.")

        # Derive the organization from the original admission, not callback subject claims.
        await self._session.scalar(
            select(OrganizationRow.id)
            .join(HumanIdentityLinkRow, HumanIdentityLinkRow.organization_id == OrganizationRow.id)
            .join(
                IdentityRecoveryAdmissionRow,
                and_(
                    IdentityRecoveryAdmissionRow.authority == HumanIdentityLinkRow.authority,
                    IdentityRecoveryAdmissionRow.subject == HumanIdentityLinkRow.subject,
                ),
            )
            .where(
                IdentityRecoveryAdmissionRow.installation_id == installation_id.value,
                IdentityRecoveryAdmissionRow.authority == authority.value,
                IdentityRecoveryAdmissionRow.flow_id == flow_id.value,
                IdentityRecoveryAdmissionRow.subject == identity.subject.value,
            )
            .with_for_update(of=OrganizationRow)
        )

        other = aliased(IdentityRecoveryAdmissionRow)
        other_pending = (
            exists()
            .where(
                other.installation_id == IdentityRecoveryAdmissionRow.installation_id,
                other.authority == IdentityRecoveryAdmissionRow.authority,
                other.subject == IdentityRecoveryAdmissionRow.subject,
                other.flow_id != IdentityRecoveryAdmissionRow.flow_id,
                other.released_at.is_(None),
            )
            .correlate(IdentityRecoveryAdmissionRow)
        )
        statement = (
            select(
                IdentityRecoveryAdmissionRow,
                Nullable(HumanIdentityLinkRow),
                Nullable(PrincipalRow),
                other_pending,
                Nullable(HumanCredentialVersionRow),
            )
            .select_from(IdentityRecoveryAdmissionRow)
            .outerjoin(
                HumanIdentityLinkRow,
                and_(
                    HumanIdentityLinkRow.authority == IdentityRecoveryAdmissionRow.authority,
                    HumanIdentityLinkRow.subject == IdentityRecoveryAdmissionRow.subject,
                ),
            )
            .outerjoin(PrincipalRow, PrincipalRow.id == HumanIdentityLinkRow.principal_id)
            .outerjoin(
                HumanCredentialVersionRow,
                and_(
                    HumanCredentialVersionRow.installation_id
                    == IdentityRecoveryAdmissionRow.installation_id,
                    HumanCredentialVersionRow.authority == IdentityRecoveryAdmissionRow.authority,
                    HumanCredentialVersionRow.subject == IdentityRecoveryAdmissionRow.subject,
                ),
            )
            .where(
                IdentityRecoveryAdmissionRow.installation_id == installation_id.value,
                IdentityRecoveryAdmissionRow.authority == authority.value,
                IdentityRecoveryAdmissionRow.flow_id == flow_id.value,
            )
            .execution_options(populate_existing=True)
        )
        result = (await self._session.execute(statement)).one_or_none()
        if result is None:
            raise ResourceNotFoundError()
        admission, link, account, has_other_pending, version = result
        if admission.subject != identity.subject.value:
            raise RuntimeError("The recovery admission changed its original identity binding.")
        principal = None
        if link is not None:
            if (
                account is None
                or account.organization_id != link.organization_id
                or account.kind is not link.principal_kind
                or account.kind is not PrincipalKind.HUMAN
            ):
                raise RuntimeError("The recovery identity link is inconsistent with its account.")
            principal = Principal(
                id=PrincipalId(account.id),
                organization_id=OrganizationId(account.organization_id),
                kind=account.kind,
                status=account.status,
            )
        return IdentityRecoveryCompletionFactsDTO(
            installation_id=installation_id,
            admission=IdentityRecoveryAdmissionDTO(
                event=IdentityRecoveryEventDTO(
                    flow_id=IdentityRecoveryFlowId(admission.flow_id),
                    identity=VerifiedHumanIdentityDTO(
                        authority=IdentityAuthority(admission.authority),
                        subject=IdentitySubject(admission.subject),
                    ),
                    event_kind=admission.event_kind,
                ),
                operation_id=OperationId(admission.operation_id),
            ),
            principal=principal,
            has_other_pending_recovery=has_other_pending,
            credential_version=None if version is None else HumanCredentialVersion(version.version),
        )

    async def _read_original_recovery_identity(
        self,
        *,
        installation_id: InstallationId,
        authority: IdentityAuthority,
        flow_id: IdentityRecoveryFlowId,
    ) -> VerifiedHumanIdentityDTO:
        """Find whose identity turn this recovery needs, without deciding release eligibility."""
        subject = await self._session.scalar(
            select(IdentityRecoveryAdmissionRow.subject)
            .where(
                IdentityRecoveryAdmissionRow.installation_id == installation_id.value,
                IdentityRecoveryAdmissionRow.authority == authority.value,
                IdentityRecoveryAdmissionRow.flow_id == flow_id.value,
            )
            .execution_options(autoflush=False)
        )
        if subject is None:
            raise ResourceNotFoundError()
        return VerifiedHumanIdentityDTO(authority, IdentitySubject(subject))
