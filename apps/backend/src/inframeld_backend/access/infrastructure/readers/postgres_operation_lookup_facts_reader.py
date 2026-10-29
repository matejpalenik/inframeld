import asyncio
from typing import override

from sqlalchemy import BigInteger, Nullable, and_, exists, literal, select
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
from inframeld_backend.access.application.dtos.operation_lookup_facts_dto import (
    OperationLookupFactsDTO,
)
from inframeld_backend.access.application.protocols.operation_lookup_facts_reader import (
    OperationLookupFactsReader,
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
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.queries.lookup_original_operation_query import (
    LookupOriginalOperationQuery,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class PostgresOperationLookupFactsReader(OperationLookupFactsReader):
    """Read current authority coherently, independently of reservation existence."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def read(
        self, *, access: AccessContextDTO, query: LookupOriginalOperationQuery
    ) -> OperationLookupFactsDTO | None:
        if query.project_id is None:
            return None
        member = exists().where(
            ProjectMembershipRow.project_id == ProjectRow.id,
            ProjectMembershipRow.principal_id == PrincipalRow.id,
        )
        grant_scope = (
            ProjectActionGrantRow.project_id == ProjectRow.id,
            ProjectActionGrantRow.recipient_principal_id == PrincipalRow.id,
            ProjectActionGrantRow.action == query.expected_authority.action_id.value,
        )
        granted = exists().where(*grant_scope)
        can_grant = exists().where(*grant_scope, ProjectActionGrantRow.can_grant.is_(True))
        pending = (
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
            binding_matches = HumanCredentialStateQueries.binding_matches_actor(evidence)
            version = Nullable(HumanCredentialStateQueries.version_for_actor(evidence))
        else:
            binding_matches = literal(False)
            version = Nullable(literal(None, BigInteger))
        statement = (
            select(
                PrincipalRow,
                ProjectRow.status,
                Nullable(InstallationIdentityRow.installation_id),
                member,
                granted,
                can_grant,
                pending,
                binding_matches,
                version,
            )
            .select_from(PrincipalRow)
            .join(
                ProjectRow,
                and_(
                    ProjectRow.id == query.project_id.value,
                    ProjectRow.organization_id == PrincipalRow.organization_id,
                ),
            )
            .outerjoin(InstallationIdentityRow, InstallationIdentityRow.singleton_key == 1)
            .where(
                PrincipalRow.id == access.actor_principal_id.value,
                PrincipalRow.organization_id == query.organization_id.value,
            )
            .execution_options(populate_existing=True)
        )
        try:
            async with asyncio.timeout(5.0):
                observed = (await self._session.execute(statement)).tuples().one_or_none()
        except (TimeoutError, OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None
        if observed is None:
            return None

        actor, status, installed, membership, use, delegation, blocked, matches, current_version = (
            observed
        )
        if installed is None:
            raise DependencyUnavailableError()
        return OperationLookupFactsDTO(
            installation_id=InstallationId(installed),
            principal=Principal(
                PrincipalId(actor.id),
                OrganizationId(actor.organization_id),
                actor.kind,
                actor.status,
            ),
            project_status=status,
            is_project_member=membership,
            has_exact_action_grant=use,
            can_grant_action=delegation,
            has_pending_recovery=blocked,
            oauth_credential_facts=HumanOAuthCredentialFactsDTO(
                matches,
                HumanCredentialVersion(current_version) if current_version is not None else None,
            )
            if isinstance(evidence, HumanOAuthCredentialBindingDTO)
            else None,
        )
