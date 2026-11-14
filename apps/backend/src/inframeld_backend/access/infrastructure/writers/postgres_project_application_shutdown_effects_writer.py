from typing import override

from sqlalchemy import DateTime, String, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.protocols.project_application_shutdown_effects_writer import (
    ProjectApplicationShutdownEffectsWriter,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.rows.application_account_row import (
    ApplicationAccountRow,
)
from inframeld_backend.access.infrastructure.rows.application_action_grant_row import (
    ApplicationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.application_key_row import ApplicationKeyRow
from inframeld_backend.access.infrastructure.rows.group_action_grant_row import GroupActionGrantRow
from inframeld_backend.access.infrastructure.rows.group_membership_row import GroupMembershipRow
from inframeld_backend.access.infrastructure.rows.model_connection_action_grant_row import (
    ModelConnectionActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class PostgresProjectApplicationShutdownEffectsWriter(ProjectApplicationShutdownEffectsWriter):
    """Persist only local shutdown effects on the caller-owned PostgreSQL session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def shutdown(
        self,
        *,
        installation_id: InstallationId,
        organization_id: OrganizationId,
        project_id: ProjectId,
    ) -> bool:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Project shutdown requires the active caller transaction.")

        with self._session.no_autoflush:
            isolation = await self._session.scalar(
                select(func.current_setting("transaction_isolation", type_=String()))
            )
            if isolation != "read committed":
                raise RuntimeError("Project shutdown requires READ COMMITTED isolation.")

            organization = await self._session.scalar(
                select(OrganizationRow.id)
                .where(OrganizationRow.id == organization_id.value)
                .with_for_update(read=True)
            )
            project = (
                (
                    await self._session.execute(
                        select(ProjectRow.id, ProjectRow.status)
                        .where(
                            ProjectRow.id == project_id.value,
                            ProjectRow.organization_id == organization_id.value,
                        )
                        .with_for_update()
                    )
                )
                .tuples()
                .one_or_none()
            )
            if organization is None or project is None:
                raise RuntimeError("Project shutdown changed its exact Organization/Project scope.")
            if project[1] is not ProjectStatus.DELETING:
                raise RuntimeError("Project shutdown requires the checked DELETING lifecycle.")

            accounts = (
                (
                    await self._session.execute(
                        select(
                            ApplicationAccountRow.principal_id, ApplicationAccountRow.principal_kind
                        )
                        .where(
                            ApplicationAccountRow.organization_id == organization_id.value,
                            ApplicationAccountRow.project_id == project_id.value,
                        )
                        .order_by(ApplicationAccountRow.principal_id)
                        .with_for_update()
                    )
                )
                .tuples()
                .all()
            )
            if any(kind is not PrincipalKind.APPLICATION for _, kind in accounts):
                raise RuntimeError("Project shutdown observed an invalid account kind.")
            account_ids = tuple(identity for identity, _ in accounts)

            principals = (
                (
                    await self._session.execute(
                        select(PrincipalRow.id, PrincipalRow.organization_id, PrincipalRow.kind)
                        .where(PrincipalRow.id.in_(account_ids))
                        .order_by(PrincipalRow.id)
                        .with_for_update()
                    )
                )
                .tuples()
                .all()
            )
            if {identity for identity, _, _ in principals} != set(account_ids) or any(
                organization != organization_id.value or kind is not PrincipalKind.APPLICATION
                for _, organization, kind in principals
            ):
                raise RuntimeError("Project shutdown changed an account's principal binding.")

            keys = (
                (
                    await self._session.execute(
                        select(
                            ApplicationKeyRow.key_id,
                            ApplicationKeyRow.installation_id,
                            ApplicationKeyRow.organization_id,
                            ApplicationKeyRow.project_id,
                            ApplicationKeyRow.created_at,
                            ApplicationKeyRow.revoked_at,
                        )
                        .where(ApplicationKeyRow.application_principal_id.in_(account_ids))
                        .order_by(
                            ApplicationKeyRow.application_principal_id, ApplicationKeyRow.key_id
                        )
                        .with_for_update()
                    )
                )
                .tuples()
                .all()
            )
            installed = await self._session.scalar(
                select(InstallationIdentityRow.installation_id).where(
                    InstallationIdentityRow.singleton_key == 1
                )
            )
            now = await self._session.scalar(
                select(func.clock_timestamp(type_=DateTime(timezone=True)))
            )
            if installed != installation_id.value or now is None:
                raise RuntimeError(
                    "Project shutdown changed its installation or current-time binding."
                )
            if any(
                installed_key != installation_id.value
                or organization != organization_id.value
                or project != project_id.value
                or (revoked_at is None and created_at > now)
                for _, installed_key, organization, project, created_at, revoked_at in keys
            ):
                raise RuntimeError("Project shutdown changed an associated key's checked binding.")

            # These are local effects only. The caller owns revision, audit and checkpoint.
            retired = (
                await self._session.scalars(
                    update(PrincipalRow)
                    .where(
                        PrincipalRow.id.in_(account_ids),
                        PrincipalRow.organization_id == organization_id.value,
                        PrincipalRow.kind == PrincipalKind.APPLICATION,
                        PrincipalRow.status != PrincipalStatus.RETIRED,
                    )
                    .values(status=PrincipalStatus.RETIRED)
                    .returning(PrincipalRow.id)
                )
            ).all()
            revoked = (
                await self._session.scalars(
                    update(ApplicationKeyRow)
                    .where(
                        ApplicationKeyRow.key_id.in_(tuple(key[0] for key in keys)),
                        ApplicationKeyRow.installation_id == installation_id.value,
                        ApplicationKeyRow.organization_id == organization_id.value,
                        ApplicationKeyRow.project_id == project_id.value,
                        ApplicationKeyRow.application_principal_id.in_(account_ids),
                        ApplicationKeyRow.revoked_at.is_(None),
                    )
                    .values(revoked_at=now)
                    .returning(ApplicationKeyRow.key_id)
                )
            ).all()
            project_grants = (
                await self._session.scalars(
                    delete(ProjectActionGrantRow)
                    .where(
                        ProjectActionGrantRow.project_id == project_id.value,
                        ProjectActionGrantRow.recipient_principal_id.in_(account_ids),
                    )
                    .returning(ProjectActionGrantRow.recipient_principal_id)
                )
            ).all()
            group_grants = (
                await self._session.scalars(
                    delete(GroupActionGrantRow)
                    .where(
                        GroupActionGrantRow.project_id == project_id.value,
                        GroupActionGrantRow.recipient_principal_id.in_(account_ids),
                    )
                    .returning(GroupActionGrantRow.recipient_principal_id)
                )
            ).all()
            connection_grants = (
                await self._session.scalars(
                    delete(ModelConnectionActionGrantRow)
                    .where(
                        ModelConnectionActionGrantRow.project_id == project_id.value,
                        ModelConnectionActionGrantRow.recipient_principal_id.in_(account_ids),
                    )
                    .returning(ModelConnectionActionGrantRow.recipient_principal_id)
                )
            ).all()
            account_grants = (
                await self._session.scalars(
                    delete(ApplicationActionGrantRow)
                    .where(
                        ApplicationActionGrantRow.project_id == project_id.value,
                        ApplicationActionGrantRow.application_principal_id.in_(account_ids),
                    )
                    .returning(ApplicationActionGrantRow.application_principal_id)
                )
            ).all()
            group_memberships = (
                await self._session.scalars(
                    delete(GroupMembershipRow)
                    .where(
                        GroupMembershipRow.project_id == project_id.value,
                        GroupMembershipRow.principal_id.in_(account_ids),
                    )
                    .returning(GroupMembershipRow.principal_id)
                )
            ).all()
            project_memberships = (
                await self._session.scalars(
                    delete(ProjectMembershipRow)
                    .where(
                        ProjectMembershipRow.project_id == project_id.value,
                        ProjectMembershipRow.principal_id.in_(account_ids),
                    )
                    .returning(ProjectMembershipRow.principal_id)
                )
            ).all()
            return bool(
                retired
                or revoked
                or project_grants
                or group_grants
                or account_grants
                or connection_grants
                or group_memberships
                or project_memberships
            )
