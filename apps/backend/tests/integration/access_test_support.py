"""Build realistic Access records for PostgreSQL integration tests."""

from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.domain.values import (
    ActionId,
    OrganizationId,
    PrincipalId,
    PrincipalKind,
    PrincipalStatus,
    ProjectId,
    ProjectStatus,
)
from inframeld_backend.access.infrastructure.persistence_models import (
    ApplicationAccountRow,
    OrganizationRow,
    PrincipalRow,
    ProjectActionGrantRow,
    ProjectMembershipRow,
    ProjectRow,
)

TEST_PROJECT_ACTION = ActionId("test-project-action")


@dataclass(frozen=True, slots=True)
class ProjectAuthorizationSeed:
    """Identify the principal and project created for an authorization test."""

    principal_id: PrincipalId
    project_id: ProjectId
    action: ActionId


@dataclass(frozen=True, slots=True)
class MultiProjectAuthorizationSeed:
    """Identify two projects with different grants for the same human principal."""

    principal_id: PrincipalId
    granted_project_id: ProjectId
    ungranted_project_id: ProjectId
    action: ActionId


async def seed_project_authorization(
    session: AsyncSession,
    *,
    is_project_member: bool,
    has_action_grant: bool,
    principal_kind: PrincipalKind = PrincipalKind.HUMAN,
    principal_status: PrincipalStatus = PrincipalStatus.ACTIVE,
) -> ProjectAuthorizationSeed:
    """Create a human or application principal with optional project membership and grant."""
    if has_action_grant and not is_project_member:
        raise ValueError("A project action grant requires project membership.")

    organization_id = OrganizationId(uuid4())
    principal_id = PrincipalId(uuid4())
    project_id = ProjectId(uuid4())

    session.add(OrganizationRow(id=organization_id, name="Support"))
    await session.flush()
    session.add_all(
        [
            PrincipalRow(
                id=principal_id,
                organization_id=organization_id,
                kind=principal_kind,
                status=principal_status,
                display_name="Alice" if principal_kind is PrincipalKind.HUMAN else "SupportBot",
            ),
            ProjectRow(
                id=project_id,
                organization_id=organization_id,
                name="Support",
                status=ProjectStatus.ACTIVE,
            ),
        ]
    )
    await session.flush()

    if principal_kind is PrincipalKind.APPLICATION:
        session.add(
            ApplicationAccountRow(
                principal_id=principal_id,
                organization_id=organization_id,
                project_id=project_id,
                principal_kind=PrincipalKind.APPLICATION,
            )
        )
        await session.flush()

    if is_project_member:
        session.add(
            ProjectMembershipRow(
                project_id=project_id,
                principal_id=principal_id,
                organization_id=organization_id,
                principal_kind=principal_kind,
                application_principal_id=(
                    principal_id if principal_kind is PrincipalKind.APPLICATION else None
                ),
            )
        )
        await session.flush()

    if has_action_grant:
        session.add(
            ProjectActionGrantRow(
                project_id=project_id,
                recipient_principal_id=principal_id,
                recipient_kind=principal_kind,
                action=TEST_PROJECT_ACTION.value,
                can_grant=False,
            )
        )
        await session.flush()

    return ProjectAuthorizationSeed(
        principal_id=principal_id,
        project_id=project_id,
        action=TEST_PROJECT_ACTION,
    )


async def seed_multi_project_authorization(
    session: AsyncSession,
) -> MultiProjectAuthorizationSeed:
    """Create Alice as a member of two projects with a grant in only one."""
    organization_id = OrganizationId(uuid4())
    principal_id = PrincipalId(uuid4())
    granted_project_id = ProjectId(uuid4())
    ungranted_project_id = ProjectId(uuid4())

    session.add(OrganizationRow(id=organization_id, name="Support"))
    await session.flush()
    session.add_all(
        [
            PrincipalRow(
                id=principal_id,
                organization_id=organization_id,
                kind=PrincipalKind.HUMAN,
                status=PrincipalStatus.ACTIVE,
                display_name="Alice",
            ),
            ProjectRow(
                id=granted_project_id,
                organization_id=organization_id,
                name="Support",
                status=ProjectStatus.ACTIVE,
            ),
            ProjectRow(
                id=ungranted_project_id,
                organization_id=organization_id,
                name="Test",
                status=ProjectStatus.ACTIVE,
            ),
        ]
    )
    await session.flush()
    session.add_all(
        [
            ProjectMembershipRow(
                project_id=project_id,
                principal_id=principal_id,
                organization_id=organization_id,
                principal_kind=PrincipalKind.HUMAN,
            )
            for project_id in (granted_project_id, ungranted_project_id)
        ]
    )
    await session.flush()
    session.add(
        ProjectActionGrantRow(
            project_id=granted_project_id,
            recipient_principal_id=principal_id,
            recipient_kind=PrincipalKind.HUMAN,
            action=TEST_PROJECT_ACTION.value,
            can_grant=False,
        )
    )
    await session.flush()

    return MultiProjectAuthorizationSeed(
        principal_id=principal_id,
        granted_project_id=granted_project_id,
        ungranted_project_id=ungranted_project_id,
        action=TEST_PROJECT_ACTION,
    )
