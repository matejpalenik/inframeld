from typing import override

from sqlalchemy import BigInteger, Nullable, and_, exists, literal, select, true
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.browser_session_authentication_dto import (
    BrowserSessionAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.human_credential_facts_dto import (
    HumanCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.dtos.project_action_grant_dto import ProjectActionGrantDTO
from inframeld_backend.access.application.dtos.project_action_grants_page_facts_dto import (
    ProjectActionGrantsPageFactsDTO,
)
from inframeld_backend.access.application.protocols.project_action_grants_facts_reader import (
    ProjectActionGrantsFactsReader,
)
from inframeld_backend.access.domain.entities.principal import Principal
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
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class PostgresProjectActionGrantsFactsReader(ProjectActionGrantsFactsReader):
    """Observe current authority and a bounded page in one PostgreSQL snapshot.

    The left lateral join retains the header even when continuation is empty.
    The application interprets these facts before disclosing any member data.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def read_page(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        action_id: ActionId,
        after: PrincipalId | None,
        limit: int,
    ) -> ProjectActionGrantsPageFactsDTO | None:
        assignment = aliased(ProjectActionGrantRow, name="stored_assignment")
        page = select(assignment).where(
            assignment.project_id == ProjectRow.id,
            assignment.action == action_id.value,
        )
        if after is not None:
            page = page.where(assignment.recipient_principal_id > after.value)
        bounded_page = (
            page.order_by(assignment.recipient_principal_id)
            .limit(limit + 1)
            .correlate(PrincipalRow, ProjectRow)
            .lateral("assignments_page")
        )
        page_assignment = aliased(ProjectActionGrantRow, bounded_page)

        is_project_member = (
            exists()
            .where(
                ProjectMembershipRow.project_id == ProjectRow.id,
                ProjectMembershipRow.organization_id == PrincipalRow.organization_id,
                ProjectMembershipRow.principal_id == PrincipalRow.id,
            )
            .correlate(PrincipalRow, ProjectRow)
        )
        has_exact_action_grant = (
            exists()
            .where(
                ProjectActionGrantRow.project_id == ProjectRow.id,
                ProjectActionGrantRow.recipient_principal_id == PrincipalRow.id,
                ProjectActionGrantRow.recipient_kind == PrincipalRow.kind,
                ProjectActionGrantRow.action == action_id.value,
            )
            .correlate(PrincipalRow, ProjectRow)
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
            .where(
                IdentityRecoveryAdmissionRow.installation_id
                == InstallationIdentityRow.installation_id,
                HumanIdentityLinkRow.principal_id == PrincipalRow.id,
                IdentityRecoveryAdmissionRow.released_at.is_(None),
            )
            .exists()
            .correlate(PrincipalRow, InstallationIdentityRow)
        )
        evidence = access.authentication_evidence
        matches_actor = (
            HumanCredentialStateQueries.binding_matches_actor(evidence)
            if isinstance(
                evidence, HumanOAuthCredentialBindingDTO | BrowserSessionAuthenticationDTO
            )
            else literal(False)
        )
        credential_version = (
            Nullable(HumanCredentialStateQueries.version_for_actor(evidence))
            if isinstance(
                evidence, HumanOAuthCredentialBindingDTO | BrowserSessionAuthenticationDTO
            )
            else Nullable(literal(None, BigInteger))
        )
        statement = (
            select(
                PrincipalRow,
                ProjectRow,
                Nullable(InstallationIdentityRow.installation_id),
                is_project_member,
                has_exact_action_grant.label("actor_has_exact_action_grant"),
                has_exact_action_grant.where(ProjectActionGrantRow.can_grant.is_(True)).label(
                    "actor_can_grant_action"
                ),
                has_pending_recovery,
                matches_actor,
                credential_version,
                Nullable(page_assignment),
            )
            .select_from(PrincipalRow)
            .join(
                ProjectRow,
                and_(
                    ProjectRow.id == project_id.value,
                    ProjectRow.organization_id == PrincipalRow.organization_id,
                ),
            )
            .outerjoin(InstallationIdentityRow, InstallationIdentityRow.singleton_key == 1)
            .outerjoin(bounded_page, true())
            .where(PrincipalRow.id == access.actor_principal_id.value)
            .order_by(page_assignment.recipient_principal_id)
            .execution_options(populate_existing=True, autoflush=False)
        )
        try:
            rows = (await self._session.execute(statement)).tuples().all()
        except (OperationalError, SqlAlchemyTimeoutError) as error:
            raise DependencyUnavailableError() from error
        if not rows:
            return None

        (
            principal,
            project,
            installed,
            membership,
            granted,
            grantable,
            recovering,
            linked,
            version,
            _,
        ) = rows[0]
        if installed is None:
            raise DependencyUnavailableError("The installation identity is not available.")

        items: list[ProjectActionGrantDTO] = []
        for _, _, _, _, _, _, _, _, _, stored_assignment in rows:
            if stored_assignment is not None:
                items.append(
                    ProjectActionGrantDTO(
                        PrincipalId(stored_assignment.recipient_principal_id),
                        ActionId(stored_assignment.action),
                        stored_assignment.can_grant,
                    )
                )

        return ProjectActionGrantsPageFactsDTO(
            installation_id=InstallationId(installed),
            organization_id=OrganizationId(principal.organization_id),
            project_id=ProjectId(project.id),
            action_id=action_id,
            action=ProjectActionFactsDTO(
                principal=Principal(
                    PrincipalId(principal.id),
                    OrganizationId(principal.organization_id),
                    principal.kind,
                    principal.status,
                ),
                has_pending_recovery=recovering,
                oauth_credential_facts=HumanCredentialFactsDTO(
                    linked, HumanCredentialVersion(version) if version is not None else None
                )
                if isinstance(
                    evidence, HumanOAuthCredentialBindingDTO | BrowserSessionAuthenticationDTO
                )
                else None,
                project_status=project.status,
                is_project_member=membership,
                has_exact_action_grant=granted,
            ),
            actor_can_grant_action=grantable,
            items=tuple(items),
        )
