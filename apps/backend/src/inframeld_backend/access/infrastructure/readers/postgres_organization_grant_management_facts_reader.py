import asyncio
from typing import override

from sqlalchemy import BigInteger, Nullable, String, and_, exists, func, literal, select
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
from inframeld_backend.access.application.dtos.organization_grant_management_facts_dto import (
    OrganizationGrantManagementFactsDTO,
)
from inframeld_backend.access.application.protocols.organization_grant_management_facts_reader import (
    OrganizationGrantManagementFactsReader,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.policy_inputs.organization_grant_candidate_policy_input import (
    OrganizationGrantCandidatePolicyInput,
)
from inframeld_backend.access.domain.value_objects.action_grant_state import ActionGrantState
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.infrastructure.readers.human_credential_state_queries import (
    HumanCredentialStateQueries,
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
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class PostgresOrganizationGrantManagementFactsReader(OrganizationGrantManagementFactsReader):
    """Observe the current attempt only after taking its exclusive Organization turn."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def lock_for_management(
        self,
        *,
        access: AccessContextDTO,
        organization_id: OrganizationId,
        recipient_principal_id: PrincipalId,
        action_id: ActionId,
    ) -> OrganizationGrantManagementFactsDTO | None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Organization grant facts require the active caller transaction.")
        try:
            async with asyncio.timeout(5):
                with self._session.no_autoflush:
                    isolation = await self._session.scalar(
                        select(func.current_setting("transaction_isolation", type_=String()))
                    )
                    if isolation != "read committed":
                        raise RuntimeError(
                            "Organization grant coordination requires READ COMMITTED."
                        )
                    locked = await self._session.scalar(
                        select(OrganizationRow.id)
                        .join(PrincipalRow, PrincipalRow.organization_id == OrganizationRow.id)
                        .where(
                            PrincipalRow.id == access.actor_principal_id.value,
                            OrganizationRow.id == organization_id.value,
                        )
                        .with_for_update(of=OrganizationRow)
                    )
                    if locked is None:
                        return None
                    installed = await self._session.scalar(
                        select(InstallationIdentityRow.installation_id).where(
                            InstallationIdentityRow.singleton_key == 1
                        )
                    )
                    if installed is None:
                        raise DependencyUnavailableError(
                            "The installation identity is unavailable."
                        )
                    installation = InstallationId(installed)
                    pending = HumanCredentialStateQueries.pending_for_principal(
                        PrincipalRow.id, installation
                    )
                    coherent = HumanCredentialStateQueries.coherent_for_principal(
                        PrincipalRow.id, organization_id, installation
                    )
                    exact_grant = (
                        exists()
                        .where(
                            OrganizationActionGrantRow.organization_id == organization_id.value,
                            OrganizationActionGrantRow.recipient_principal_id == PrincipalRow.id,
                            OrganizationActionGrantRow.recipient_kind == PrincipalRow.kind,
                            OrganizationActionGrantRow.action == action_id.value,
                            OrganizationActionGrantRow.can_grant.is_(True),
                        )
                        .correlate(PrincipalRow)
                    )
                    evidence = access.authentication_evidence
                    if isinstance(evidence, HumanOAuthCredentialBindingDTO):
                        matches = HumanCredentialStateQueries.binding_matches_actor(evidence)
                        version = Nullable(HumanCredentialStateQueries.version_for_actor(evidence))
                    else:
                        matches = literal(False)
                        version = Nullable(literal(None, BigInteger))
                    actor = (
                        (
                            await self._session.execute(
                                select(
                                    PrincipalRow,
                                    OrganizationRow.access_revision,
                                    exact_grant,
                                    pending,
                                    matches,
                                    version,
                                )
                                .join(
                                    OrganizationRow,
                                    OrganizationRow.id == PrincipalRow.organization_id,
                                )
                                .where(
                                    PrincipalRow.id == access.actor_principal_id.value,
                                    OrganizationRow.id == organization_id.value,
                                )
                                .execution_options(populate_existing=True)
                            )
                        )
                        .tuples()
                        .one_or_none()
                    )
                    if actor is None:
                        return None
                    recipient = (
                        (
                            await self._session.execute(
                                select(
                                    PrincipalRow,
                                    pending,
                                    coherent,
                                    Nullable(OrganizationActionGrantRow.can_grant),
                                )
                                .outerjoin(
                                    OrganizationActionGrantRow,
                                    and_(
                                        OrganizationActionGrantRow.organization_id
                                        == organization_id.value,
                                        OrganizationActionGrantRow.recipient_principal_id
                                        == PrincipalRow.id,
                                        OrganizationActionGrantRow.recipient_kind
                                        == PrincipalRow.kind,
                                        OrganizationActionGrantRow.action == action_id.value,
                                    ),
                                )
                                .where(
                                    PrincipalRow.id == recipient_principal_id.value,
                                    PrincipalRow.organization_id == organization_id.value,
                                )
                                .execution_options(populate_existing=True)
                            )
                        )
                        .tuples()
                        .one_or_none()
                    )
                    candidates = (
                        (
                            await self._session.execute(
                                select(PrincipalRow, pending, coherent)
                                .where(
                                    PrincipalRow.organization_id == organization_id.value,
                                    PrincipalRow.id != recipient_principal_id.value,
                                    exact_grant,
                                )
                                .execution_options(populate_existing=True)
                            )
                        )
                        .tuples()
                        .all()
                    )

                    return OrganizationGrantManagementFactsDTO(
                        installation_id=installation,
                        organization_id=organization_id,
                        action_id=action_id,
                        access_revision=actor[1],
                        actor=self._principal(actor[0]),
                        actor_can_grant=actor[2],
                        actor_has_pending_recovery=actor[3],
                        actor_oauth_credential_facts=HumanOAuthCredentialFactsDTO(
                            binding_matches_actor=actor[4],
                            current_version=HumanCredentialVersion(actor[5])
                            if actor[5] is not None
                            else None,
                        )
                        if isinstance(evidence, HumanOAuthCredentialBindingDTO)
                        else None,
                        recipient=self._principal(recipient[0]) if recipient is not None else None,
                        recipient_has_pending_recovery=recipient[1]
                        if recipient is not None
                        else False,
                        recipient_has_coherent_identity=recipient[2]
                        if recipient is not None
                        else False,
                        assignment=ActionGrantState(
                            can_grant=recipient[3] if recipient is not None else None
                        ),
                        other_grantors=tuple(
                            OrganizationGrantCandidatePolicyInput(
                                principal=self._principal(row),
                                has_pending_recovery=blocked,
                                has_coherent_identity=identity,
                                can_grant=True,
                            )
                            for row, blocked, identity in candidates
                        ),
                    )
        except (TimeoutError, OperationalError, SqlAlchemyTimeoutError) as error:
            raise DependencyUnavailableError() from error

    @staticmethod
    def _principal(row: PrincipalRow) -> Principal:
        return Principal(
            id=PrincipalId(row.id),
            organization_id=OrganizationId(row.organization_id),
            kind=row.kind,
            status=row.status,
        )
