from uuid import UUID

from sqlalchemy import (
    SQLColumnExpression,
    and_,
    exists,
    or_,
    select,
)
from sqlalchemy.sql.selectable import Exists

from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
)
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_admission_row import (
    IdentityRecoveryAdmissionRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


class ProjectPrincipalQueries:
    """Compose existing membership and admitted-human eligibility observations."""

    @staticmethod
    def membership(
        principal: SQLColumnExpression[UUID], project: ProjectId, organization: OrganizationId
    ) -> Exists:
        """Build the current Project-membership predicate for a candidate human."""
        return (
            exists()
            .where(
                ProjectMembershipRow.project_id == project.value,
                ProjectMembershipRow.organization_id == organization.value,
                ProjectMembershipRow.principal_id == principal,
            )
            .correlate_except(ProjectMembershipRow)
        )

    @staticmethod
    def pending(principal: SQLColumnExpression[UUID], installation: InstallationId) -> Exists:
        """Include unreleased recovery blocks when observing candidate eligibility."""
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
    def coherent_identity(
        principal: SQLColumnExpression[UUID],
        organization: OrganizationId,
        installation: InstallationId,
    ) -> Exists:
        """Require one coherent admitted identity when observing a replacement candidate."""
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
