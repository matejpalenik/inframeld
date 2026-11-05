import asyncio
from typing import final, override
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Nullable,
    SQLColumnExpression,
    String,
    and_,
    exists,
    func,
    literal,
    or_,
    select,
)
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql.selectable import Exists

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_facts_dto import (
    HumanOAuthCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.project_action_grant_management_facts_dto import (
    ProjectActionGrantManagementFactsDTO,
)
from inframeld_backend.access.application.dtos.project_grant_change_facts_dto import (
    ProjectGrantChangeFactsDTO,
)
from inframeld_backend.access.application.protocols.project_grant_change_facts_reader import (
    ProjectGrantChangeFactsReader,
)
from inframeld_backend.access.application.protocols.project_grant_management_facts_reader import (
    ProjectGrantManagementFactsReader,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.policy_inputs.project_departure_candidate_policy_input import (
    ProjectDepartureCandidatePolicyInput,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.readers.human_credential_state_queries import (
    HumanCredentialStateQueries,
)
from inframeld_backend.access.infrastructure.rows.application_account_row import (
    ApplicationAccountRow,
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
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import (
    ProjectMembershipRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)

_GRANT_FACTS_TIMEOUT_SECONDS = 5.0


def _to_principal(row: PrincipalRow) -> Principal:
    return Principal(
        id=PrincipalId(row.id),
        organization_id=OrganizationId(row.organization_id),
        kind=row.kind,
        status=row.status,
    )


@final
class PostgresProjectGrantChangeFactsReader(
    ProjectGrantChangeFactsReader, ProjectGrantManagementFactsReader
):
    """Acquire Access locks and load facts within one five-second database deadline.

    The caller owns the transaction and retains acquired locks until commit or
    rollback. Deadline expiry requires the caller to roll back.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def read_for_management(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        recipient_principal_id: PrincipalId,
        action_id: ActionId,
    ) -> ProjectActionGrantManagementFactsDTO | None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Grant management requires the active caller transaction.")
        try:
            async with asyncio.timeout(_GRANT_FACTS_TIMEOUT_SECONDS):
                with self._session.no_autoflush:
                    isolation = await self._session.scalar(
                        select(func.current_setting("transaction_isolation", type_=String()))
                    )
                    if isolation != "read committed":
                        raise RuntimeError("Grant coordination requires READ COMMITTED isolation.")
                    grant = await self._read_for_change(
                        access=access,
                        project_id=project_id,
                        recipient_principal_id=recipient_principal_id,
                        action_id=action_id,
                    )
                    if grant is None:
                        return None
                    installed = await self._session.scalar(
                        select(InstallationIdentityRow.installation_id).where(
                            InstallationIdentityRow.singleton_key == 1
                        )
                    )
                    if installed is None:
                        raise DependencyUnavailableError(
                            "The installation identity is not available."
                        )
                    installation = InstallationId(installed)
                    organization = grant.actor.organization_id
                    recipient = (
                        (
                            await self._session.execute(
                                select(
                                    self._pending(PrincipalRow.id, installation).label(
                                        "recipient_pending"
                                    ),
                                    self._coherent_identity(
                                        PrincipalRow.id, organization, installation
                                    ).label("recipient_coherent"),
                                    exists()
                                    .where(
                                        ApplicationAccountRow.principal_id == PrincipalRow.id,
                                        ApplicationAccountRow.project_id == project_id.value,
                                        ApplicationAccountRow.organization_id == organization.value,
                                        ApplicationAccountRow.principal_kind == PrincipalRow.kind,
                                    )
                                    .correlate(PrincipalRow)
                                    .label("recipient_application_bound"),
                                ).where(
                                    PrincipalRow.id == recipient_principal_id.value,
                                    PrincipalRow.organization_id == organization.value,
                                )
                            )
                        )
                        .tuples()
                        .one_or_none()
                    )
                    exact_grant = (
                        exists()
                        .where(
                            ProjectActionGrantRow.project_id == project_id.value,
                            ProjectActionGrantRow.recipient_principal_id == PrincipalRow.id,
                            ProjectActionGrantRow.recipient_kind == PrincipalRow.kind,
                            ProjectActionGrantRow.action == action_id.value,
                            ProjectActionGrantRow.can_grant.is_(True),
                        )
                        .correlate(PrincipalRow)
                    )
                    candidates = (
                        (
                            await self._session.execute(
                                select(
                                    PrincipalRow,
                                    self._pending(PrincipalRow.id, installation).label(
                                        "candidate_pending"
                                    ),
                                    exists()
                                    .where(
                                        ProjectMembershipRow.project_id == project_id.value,
                                        ProjectMembershipRow.organization_id == organization.value,
                                        ProjectMembershipRow.principal_id == PrincipalRow.id,
                                    )
                                    .correlate(PrincipalRow)
                                    .label("candidate_member"),
                                    self._coherent_identity(
                                        PrincipalRow.id, organization, installation
                                    ).label("candidate_coherent"),
                                    exact_grant.label("candidate_can_grant"),
                                )
                                .where(
                                    PrincipalRow.organization_id == organization.value,
                                    PrincipalRow.kind == PrincipalKind.HUMAN,
                                    PrincipalRow.id != recipient_principal_id.value,
                                    exact_grant,
                                )
                                .execution_options(populate_existing=True, autoflush=False)
                            )
                        )
                        .tuples()
                        .all()
                    )
                    return ProjectActionGrantManagementFactsDTO(
                        installation_id=installation,
                        organization_id=organization,
                        project_id=project_id,
                        action_id=action_id,
                        grant=grant,
                        recipient_has_pending_recovery=recipient[0]
                        if recipient is not None
                        else False,
                        recipient_has_coherent_identity=recipient[1]
                        if recipient is not None
                        else False,
                        recipient_application_is_project_bound=recipient[2]
                        if recipient is not None
                        else False,
                        other_grantors=tuple(
                            ProjectDepartureCandidatePolicyInput(
                                principal=_to_principal(principal),
                                has_pending_recovery=pending,
                                is_project_member=member,
                                has_coherent_identity=coherent,
                                can_grant=can_grant,
                                is_group_member=False,
                                is_group_manager=False,
                            )
                            for principal, pending, member, coherent, can_grant in candidates
                        ),
                    )
        except (TimeoutError, OperationalError, SqlAlchemyTimeoutError) as error:
            raise DependencyUnavailableError() from error

    @staticmethod
    def _pending(principal: SQLColumnExpression[UUID], installation: InstallationId) -> Exists:
        return (
            select(IdentityRecoveryAdmissionRow.operation_id)
            .join(
                HumanIdentityLinkRow,
                and_(
                    HumanIdentityLinkRow.authority == IdentityRecoveryAdmissionRow.authority,
                    HumanIdentityLinkRow.subject == IdentityRecoveryAdmissionRow.subject,
                ),
            )
            .where(
                IdentityRecoveryAdmissionRow.installation_id == installation.value,
                HumanIdentityLinkRow.principal_id == principal,
                IdentityRecoveryAdmissionRow.released_at.is_(None),
            )
            .exists()
            .correlate_except(IdentityRecoveryAdmissionRow, HumanIdentityLinkRow)
        )

    @staticmethod
    def _coherent_identity(
        principal: SQLColumnExpression[UUID],
        organization: OrganizationId,
        installation: InstallationId,
    ) -> Exists:
        version = (
            exists()
            .where(
                HumanCredentialVersionRow.installation_id == installation.value,
                HumanCredentialVersionRow.authority == HumanIdentityLinkRow.authority,
                HumanCredentialVersionRow.subject == HumanIdentityLinkRow.subject,
            )
            .correlate(HumanIdentityLinkRow)
        )
        history = (
            exists()
            .where(
                IdentityRecoveryAdmissionRow.installation_id == installation.value,
                IdentityRecoveryAdmissionRow.authority == HumanIdentityLinkRow.authority,
                IdentityRecoveryAdmissionRow.subject == HumanIdentityLinkRow.subject,
            )
            .correlate(HumanIdentityLinkRow)
        )
        return (
            exists()
            .where(
                HumanIdentityLinkRow.principal_id == principal,
                HumanIdentityLinkRow.organization_id == organization.value,
                HumanIdentityLinkRow.principal_kind == PrincipalKind.HUMAN,
                or_(version, ~history),
            )
            .correlate_except(HumanIdentityLinkRow)
        )

    @override
    async def read_for_change(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        recipient_principal_id: PrincipalId,
        action_id: ActionId,
    ) -> ProjectGrantChangeFactsDTO | None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + _GRANT_FACTS_TIMEOUT_SECONDS
        try:
            async with asyncio.timeout_at(deadline):
                facts = await self._read_for_change(
                    access=access,
                    project_id=project_id,
                    recipient_principal_id=recipient_principal_id,
                    action_id=action_id,
                )
                if loop.time() >= deadline:
                    raise TimeoutError()
                return facts
        except TimeoutError as error:
            raise DependencyUnavailableError(
                "Grant authorization exceeded its database deadline."
            ) from error

    async def _read_for_change(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        recipient_principal_id: PrincipalId,
        action_id: ActionId,
    ) -> ProjectGrantChangeFactsDTO | None:
        """Observe the actor and target under the grant workflow coordination locks."""
        actor_organization_id = await self._session.scalar(
            select(PrincipalRow.organization_id).where(
                PrincipalRow.id == access.actor_principal_id.value
            )
        )
        if actor_organization_id is None:
            return None

        # Acquire the organization lock before the project lock.
        locked_organization_id = await self._session.scalar(
            select(OrganizationRow.id)
            .where(OrganizationRow.id == actor_organization_id)
            .with_for_update(read=True)
        )
        if locked_organization_id is None:
            return None

        locked_project_id = await self._session.scalar(
            select(ProjectRow.id)
            .where(
                ProjectRow.id == project_id.value,
                ProjectRow.organization_id == locked_organization_id,
            )
            .with_for_update()
        )
        if locked_project_id is None:
            return None

        recipient = aliased(PrincipalRow, name="recipient")

        actor_is_member = exists().where(
            ProjectMembershipRow.project_id == ProjectRow.id,
            ProjectMembershipRow.principal_id == PrincipalRow.id,
        )
        recipient_is_member = exists().where(
            ProjectMembershipRow.project_id == ProjectRow.id,
            ProjectMembershipRow.principal_id == recipient.id,
        )
        actor_can_grant = exists().where(
            ProjectActionGrantRow.project_id == ProjectRow.id,
            ProjectActionGrantRow.recipient_principal_id == PrincipalRow.id,
            ProjectActionGrantRow.action == action_id.value,
            ProjectActionGrantRow.can_grant.is_(True),
        )
        installation_available = exists().where(
            InstallationIdentityRow.singleton_key == 1,
        )
        has_pending_recovery = (
            select(IdentityRecoveryAdmissionRow.operation_id)
            .join(
                HumanIdentityLinkRow,
                and_(
                    HumanIdentityLinkRow.authority == IdentityRecoveryAdmissionRow.authority,
                    HumanIdentityLinkRow.subject == IdentityRecoveryAdmissionRow.subject,
                ),
            )
            .join(
                InstallationIdentityRow,
                InstallationIdentityRow.installation_id
                == IdentityRecoveryAdmissionRow.installation_id,
            )
            .where(
                InstallationIdentityRow.singleton_key == 1,
                HumanIdentityLinkRow.principal_id == PrincipalRow.id,
                IdentityRecoveryAdmissionRow.released_at.is_(None),
            )
            .exists()
            .correlate(PrincipalRow)
        )

        evidence = access.authentication_evidence
        if isinstance(evidence, HumanOAuthCredentialBindingDTO):
            binding_matches_actor = HumanCredentialStateQueries.binding_matches_actor(evidence)
            credential_version = Nullable(HumanCredentialStateQueries.version_for_actor(evidence))
        else:
            binding_matches_actor = literal(False)
            credential_version = Nullable(literal(None, BigInteger))

        statement = (
            select(
                PrincipalRow,
                Nullable(recipient),
                ProjectRow,
                actor_is_member,
                recipient_is_member,
                actor_can_grant,
                installation_available,
                has_pending_recovery,
                binding_matches_actor,
                credential_version,
            )
            .select_from(PrincipalRow)
            .join(
                ProjectRow,
                and_(
                    ProjectRow.id == locked_project_id,
                    ProjectRow.organization_id == PrincipalRow.organization_id,
                ),
            )
            .outerjoin(
                recipient,
                and_(
                    recipient.id == recipient_principal_id.value,
                    recipient.organization_id == PrincipalRow.organization_id,
                ),
            )
            .where(
                PrincipalRow.id == access.actor_principal_id.value,
                PrincipalRow.organization_id == locked_organization_id,
            )
            .execution_options(populate_existing=True)
        )

        result = await self._session.execute(statement)
        row = result.tuples().one_or_none()
        if row is None:
            return None

        (
            actor_row,
            recipient_row,
            project_row,
            actor_member,
            recipient_member,
            can_grant,
            has_installation,
            pending_recovery,
            matches_actor,
            current_credential_version,
        ) = row

        if not has_installation:
            raise DependencyUnavailableError("The installation identity is not available.")

        return ProjectGrantChangeFactsDTO(
            actor=_to_principal(actor_row),
            has_pending_recovery=pending_recovery,
            oauth_credential_facts=(
                HumanOAuthCredentialFactsDTO(
                    binding_matches_actor=matches_actor,
                    current_version=HumanCredentialVersion(current_credential_version)
                    if current_credential_version is not None
                    else None,
                )
                if isinstance(evidence, HumanOAuthCredentialBindingDTO)
                else None
            ),
            recipient=(_to_principal(recipient_row) if recipient_row is not None else None),
            project_status=project_row.status,
            project_access_revision=project_row.access_revision,
            actor_is_project_member=actor_member,
            recipient_is_project_member=recipient_member,
            actor_can_grant_action=can_grant,
        )
