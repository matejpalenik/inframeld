from uuid import UUID

from sqlalchemy import BigInteger, Nullable, and_, exists, literal, select
from sqlalchemy.sql import Select

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.browser_session_authentication_dto import (
    BrowserSessionAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
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
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class ProjectActorQueries:
    """Compose current actor observations for Project-scoped administration and metadata reads."""

    @staticmethod
    def header(
        access: AccessContextDTO, project_id: ProjectId
    ) -> Select[tuple[PrincipalRow, ProjectRow, UUID | None, bool, bool, bool, int | None]]:
        membership = (
            exists()
            .where(
                ProjectMembershipRow.project_id == ProjectRow.id,
                ProjectMembershipRow.organization_id == PrincipalRow.organization_id,
                ProjectMembershipRow.principal_id == PrincipalRow.id,
            )
            .correlate(PrincipalRow, ProjectRow)
        )
        recovering = (
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
        linked = (
            HumanCredentialStateQueries.binding_matches_actor(evidence)
            if isinstance(
                evidence, HumanOAuthCredentialBindingDTO | BrowserSessionAuthenticationDTO
            )
            else literal(False)
        )
        version = (
            Nullable(HumanCredentialStateQueries.version_for_actor(evidence))
            if isinstance(
                evidence, HumanOAuthCredentialBindingDTO | BrowserSessionAuthenticationDTO
            )
            else Nullable(literal(None, BigInteger))
        )
        return (
            select(
                PrincipalRow,
                ProjectRow,
                Nullable(InstallationIdentityRow.installation_id),
                membership,
                recovering,
                linked,
                version,
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
            .where(PrincipalRow.id == access.actor_principal_id.value)
            .execution_options(populate_existing=True, autoflush=False)
        )
