from datetime import datetime
from uuid import UUID

from sqlalchemy import ColumnElement, DateTime, Nullable, Select, and_, exists, func, select

from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.application_key_id import ApplicationKeyId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.rows.application_account_row import (
    ApplicationAccountRow,
)
from inframeld_backend.access.infrastructure.rows.application_key_row import ApplicationKeyRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class ApplicationKeyStateQueries:
    """Compose non-secret observations without owning sessions, locks or authorization."""

    @staticmethod
    def account_scope(principal_id: PrincipalId) -> Select[tuple[UUID, UUID]]:
        return select(
            ApplicationAccountRow.organization_id, ApplicationAccountRow.project_id
        ).where(ApplicationAccountRow.principal_id == principal_id.value)

    @staticmethod
    def local_account(
        principal_id: PrincipalId,
    ) -> Select[tuple[PrincipalRow, UUID, ProjectStatus, bool, bool]]:
        member = exists().where(
            ProjectMembershipRow.project_id == ApplicationAccountRow.project_id,
            ProjectMembershipRow.principal_id == PrincipalRow.id,
            ProjectMembershipRow.organization_id == ApplicationAccountRow.organization_id,
            ProjectMembershipRow.principal_kind == PrincipalRow.kind,
            ProjectMembershipRow.application_principal_id == ApplicationAccountRow.principal_id,
        )
        coherent = and_(
            PrincipalRow.organization_id == ApplicationAccountRow.organization_id,
            ProjectRow.organization_id == ApplicationAccountRow.organization_id,
            PrincipalRow.kind == ApplicationAccountRow.principal_kind,
        )
        return (
            select(
                PrincipalRow, ApplicationAccountRow.project_id, ProjectRow.status, member, coherent
            )
            .select_from(PrincipalRow)
            .join(ApplicationAccountRow, ApplicationAccountRow.principal_id == PrincipalRow.id)
            .join(ProjectRow, ProjectRow.id == ApplicationAccountRow.project_id)
            .where(PrincipalRow.id == principal_id.value)
            .execution_options(populate_existing=True, autoflush=False)
        )

    @staticmethod
    def key_scope(
        *,
        key_id: ApplicationKeyId,
        principal_id: PrincipalId,
        organization_id: OrganizationId,
        project_id: ProjectId,
    ) -> ColumnElement[bool]:
        return and_(
            ApplicationKeyRow.key_id == key_id.value,
            ApplicationKeyRow.application_principal_id == principal_id.value,
            ApplicationKeyRow.organization_id == organization_id.value,
            ApplicationKeyRow.project_id == project_id.value,
        )

    @staticmethod
    def current_key(
        *,
        key_id: ApplicationKeyId,
        principal_id: PrincipalId,
        organization_id: OrganizationId,
        project_id: ProjectId,
    ) -> Select[
        tuple[
            UUID,
            UUID | None,
            UUID | None,
            UUID | None,
            UUID | None,
            str | None,
            list[str] | None,
            datetime | None,
            datetime | None,
            datetime,
            bool,
        ]
    ]:
        """Select current database time only when executed after the caller's waits."""
        account_matches = exists().where(
            ApplicationAccountRow.principal_id == principal_id.value,
            ApplicationAccountRow.organization_id == organization_id.value,
            ApplicationAccountRow.project_id == project_id.value,
            PrincipalRow.id == ApplicationAccountRow.principal_id,
            PrincipalRow.organization_id == ApplicationAccountRow.organization_id,
            PrincipalRow.kind == ApplicationAccountRow.principal_kind,
        )
        return (
            select(
                InstallationIdentityRow.installation_id,
                Nullable(ApplicationKeyRow.application_principal_id),
                Nullable(ApplicationKeyRow.organization_id),
                Nullable(ApplicationKeyRow.project_id),
                Nullable(ApplicationKeyRow.installation_id),
                Nullable(ApplicationKeyRow.audience),
                Nullable(ApplicationKeyRow.allowed_adapters),
                Nullable(ApplicationKeyRow.expires_at),
                ApplicationKeyRow.revoked_at,
                func.clock_timestamp(type_=DateTime(timezone=True)),
                and_(ApplicationKeyRow.key_id.is_not(None), account_matches),
            )
            .select_from(InstallationIdentityRow)
            .outerjoin(
                ApplicationKeyRow,
                ApplicationKeyStateQueries.key_scope(
                    key_id=key_id,
                    principal_id=principal_id,
                    organization_id=organization_id,
                    project_id=project_id,
                ),
            )
            .where(InstallationIdentityRow.singleton_key == 1)
            .execution_options(autoflush=False)
        )
