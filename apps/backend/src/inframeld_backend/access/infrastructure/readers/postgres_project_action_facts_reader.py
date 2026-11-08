import asyncio
from typing import final, override

from sqlalchemy import BigInteger, Nullable, String, and_, exists, func, literal, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_key_authentication_dto import (
    ApplicationKeyAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.application_key_verification_profile_dto import (
    ApplicationKeyVerificationProfileDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_facts_dto import (
    HumanOAuthCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.dtos.project_action_target_dto import (
    ProjectActionTargetDTO,
)
from inframeld_backend.access.application.protocols.project_action_facts_reader import (
    ProjectActionFactsReader,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.mappers.postgres_application_key_facts_mapper import (
    PostgresApplicationKeyFactsMapper,
)
from inframeld_backend.access.infrastructure.readers.application_key_state_queries import (
    ApplicationKeyStateQueries,
)
from inframeld_backend.access.infrastructure.readers.human_credential_state_queries import (
    HumanCredentialStateQueries,
)
from inframeld_backend.access.infrastructure.rows.application_account_row import (
    ApplicationAccountRow,
)
from inframeld_backend.access.infrastructure.rows.application_key_row import ApplicationKeyRow
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
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


@final
class PostgresProjectActionFactsReader(ProjectActionFactsReader):
    """Read current authority within the caller's session and transaction.

    Application evidence requires a trusted profile and READ COMMITTED. Its
    ordered shared locks remain held until caller commit or rollback. Human
    credential and recovery observations retain their existing query.
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        application_key_profile: ApplicationKeyVerificationProfileDTO | None = None,
    ) -> None:
        self._session = session
        self._application_key_profile = application_key_profile

    @override
    async def read_action_facts(
        self, *, access: AccessContextDTO, action_id: ActionId, target: ProjectActionTargetDTO
    ) -> ProjectActionFactsDTO | None:
        if isinstance(access.authentication_evidence, ApplicationKeyAuthenticationDTO):
            return await self._read_application_facts(access, action_id, target)

        is_project_member = exists().where(
            ProjectMembershipRow.project_id == ProjectRow.id,
            ProjectMembershipRow.principal_id == PrincipalRow.id,
        )

        has_exact_action_grant = exists().where(
            ProjectActionGrantRow.project_id == ProjectRow.id,
            ProjectActionGrantRow.recipient_principal_id == PrincipalRow.id,
            ProjectActionGrantRow.action == action_id.value,
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
                ProjectRow.status,
                is_project_member,
                has_exact_action_grant,
                installation_available,
                has_pending_recovery,
                binding_matches_actor,
                credential_version,
            )
            .select_from(PrincipalRow)
            .join(
                ProjectRow,
                and_(
                    ProjectRow.id == target.project_id.value,
                    ProjectRow.organization_id == PrincipalRow.organization_id,
                ),
            )
            .where(PrincipalRow.id == access.actor_principal_id.value)
            .execution_options(populate_existing=True)
        )

        result = await self._session.execute(statement)
        row = result.tuples().one_or_none()

        if row is None:
            return None

        (
            principal_row,
            project_status,
            member,
            granted,
            has_installation,
            pending_recovery,
            matches_actor,
            current_credential_version,
        ) = row

        if not has_installation:
            raise DependencyUnavailableError("The installation identity is not available.")

        principal = Principal(
            id=PrincipalId(principal_row.id),
            organization_id=OrganizationId(principal_row.organization_id),
            kind=principal_row.kind,
            status=principal_row.status,
        )

        return ProjectActionFactsDTO(
            principal=principal,
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
            project_status=project_status,
            is_project_member=member,
            has_exact_action_grant=granted,
        )

    async def _read_application_facts(
        self, access: AccessContextDTO, action_id: ActionId, target: ProjectActionTargetDTO
    ) -> ProjectActionFactsDTO | None:
        profile = self._application_key_profile
        if profile is None:
            raise DependencyUnavailableError("The application verification profile is unavailable.")
        evidence = access.authentication_evidence
        if not isinstance(evidence, ApplicationKeyAuthenticationDTO):
            raise RuntimeError("Application facts require application-key evidence.")

        try:
            async with asyncio.timeout(5.0):
                with self._session.no_autoflush:
                    isolation = await self._session.scalar(
                        select(func.current_setting("transaction_isolation", type_=String()))
                    )
                    if isolation != "read committed":
                        raise RuntimeError(
                            "Application authorization requires READ COMMITTED isolation."
                        )
                    scope = (
                        (
                            await self._session.execute(
                                ApplicationKeyStateQueries.account_scope(access.actor_principal_id)
                            )
                        )
                        .tuples()
                        .one_or_none()
                    )
                    if scope is None:
                        principal_kind = await self._session.scalar(
                            select(PrincipalRow.kind).where(
                                PrincipalRow.id == access.actor_principal_id.value
                            )
                        )
                        if (
                            principal_kind is not None
                            and principal_kind is not PrincipalKind.APPLICATION
                        ):
                            raise RuntimeError(
                                "Authentication evidence does not match the principal kind."
                            )
                        return None
                    organization, project = scope
                    if target.project_id.value != project:
                        return None
                    locked_organization = await self._session.scalar(
                        select(OrganizationRow.id)
                        .where(OrganizationRow.id == organization)
                        .with_for_update(read=True)
                    )
                    if locked_organization is None:
                        return None
                    locked_project = await self._session.scalar(
                        select(ProjectRow.id)
                        .where(ProjectRow.id == project, ProjectRow.organization_id == organization)
                        .with_for_update(read=True)
                    )
                    if locked_project is None:
                        return None
                    organization_id, project_id = OrganizationId(organization), ProjectId(project)
                    key_scope = ApplicationKeyStateQueries.key_scope(
                        key_id=evidence.key_id,
                        principal_id=access.actor_principal_id,
                        organization_id=organization_id,
                        project_id=project_id,
                    )
                    await self._session.scalar(
                        select(ApplicationKeyRow.key_id).where(key_scope).with_for_update(read=True)
                    )

                    local = (
                        (
                            await self._session.execute(
                                ApplicationKeyStateQueries.local_account(
                                    access.actor_principal_id
                                ).where(
                                    ApplicationAccountRow.organization_id == organization,
                                    ApplicationAccountRow.project_id == target.project_id.value,
                                    ApplicationAccountRow.project_id == project,
                                )
                            )
                        )
                        .tuples()
                        .one_or_none()
                    )
                    if local is None:
                        return None
                    principal, _project_id, project_status, member, coherent = local
                    granted = await self._session.scalar(
                        select(
                            exists().where(
                                ProjectActionGrantRow.project_id == target.project_id.value,
                                ProjectActionGrantRow.recipient_principal_id
                                == access.actor_principal_id.value,
                                ProjectActionGrantRow.recipient_kind == PrincipalKind.APPLICATION,
                                ProjectActionGrantRow.action == action_id.value,
                            )
                        )
                    )
                    # Last observation uses current database UTC after all coordination waits.
                    key = (
                        (
                            await self._session.execute(
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
                    return ProjectActionFactsDTO(
                        principal=Principal(
                            id=PrincipalId(principal.id),
                            organization_id=OrganizationId(principal.organization_id),
                            kind=principal.kind,
                            status=principal.status,
                        ),
                        has_pending_recovery=False,
                        oauth_credential_facts=None,
                        project_status=project_status,
                        is_project_member=member and coherent,
                        has_exact_action_grant=granted is True,
                        application_key_facts=PostgresApplicationKeyFactsMapper.to_facts(
                            key, evidence=evidence, profile=profile
                        ),
                    )
        except (TimeoutError, OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None
