"""Build realistic Access records for PostgreSQL integration tests."""

from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.authentication.verified_human_identity import (
    VerifiedHumanIdentity,
)
from inframeld_backend.access.domain.action_values import ActionId
from inframeld_backend.access.domain.organization_values import OrganizationId
from inframeld_backend.access.domain.principal import (
    Principal,
    PrincipalId,
    PrincipalKind,
    PrincipalStatus,
)
from inframeld_backend.access.domain.project_values import ProjectId, ProjectStatus
from inframeld_backend.access.infrastructure.postgres.models.application_account_row import (
    ApplicationAccountRow,
)
from inframeld_backend.access.infrastructure.postgres.models.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.postgres.models.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.postgres.models.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.postgres.models.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.postgres.models.project_membership_row import (
    ProjectMembershipRow,
)
from inframeld_backend.access.infrastructure.postgres.models.project_row import ProjectRow

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

    session.add(OrganizationRow(id=organization_id.value, name="Support"))
    await session.flush()
    session.add_all(
        [
            PrincipalRow(
                id=principal_id.value,
                organization_id=organization_id.value,
                kind=principal_kind,
                status=principal_status,
                display_name="Alice" if principal_kind is PrincipalKind.HUMAN else "SupportBot",
            ),
            ProjectRow(
                id=project_id.value,
                organization_id=organization_id.value,
                name="Support",
                status=ProjectStatus.ACTIVE,
            ),
        ]
    )
    await session.flush()

    if principal_kind is PrincipalKind.APPLICATION:
        session.add(
            ApplicationAccountRow(
                principal_id=principal_id.value,
                organization_id=organization_id.value,
                project_id=project_id.value,
                principal_kind=PrincipalKind.APPLICATION,
            )
        )
        await session.flush()

    if is_project_member:
        session.add(
            ProjectMembershipRow(
                project_id=project_id.value,
                principal_id=principal_id.value,
                organization_id=organization_id.value,
                principal_kind=principal_kind,
                application_principal_id=(
                    principal_id.value if principal_kind is PrincipalKind.APPLICATION else None
                ),
            )
        )
        await session.flush()

    if has_action_grant:
        session.add(
            ProjectActionGrantRow(
                project_id=project_id.value,
                recipient_principal_id=principal_id.value,
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

    session.add(OrganizationRow(id=organization_id.value, name="Support"))
    await session.flush()
    session.add_all(
        [
            PrincipalRow(
                id=principal_id.value,
                organization_id=organization_id.value,
                kind=PrincipalKind.HUMAN,
                status=PrincipalStatus.ACTIVE,
                display_name="Alice",
            ),
            ProjectRow(
                id=granted_project_id.value,
                organization_id=organization_id.value,
                name="Support",
                status=ProjectStatus.ACTIVE,
            ),
            ProjectRow(
                id=ungranted_project_id.value,
                organization_id=organization_id.value,
                name="Test",
                status=ProjectStatus.ACTIVE,
            ),
        ]
    )
    await session.flush()
    session.add_all(
        [
            ProjectMembershipRow(
                project_id=project_id.value,
                principal_id=principal_id.value,
                organization_id=organization_id.value,
                principal_kind=PrincipalKind.HUMAN,
            )
            for project_id in (granted_project_id, ungranted_project_id)
        ]
    )
    await session.flush()
    session.add(
        ProjectActionGrantRow(
            project_id=granted_project_id.value,
            recipient_principal_id=principal_id.value,
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


async def seed_linked_human(
    session: AsyncSession,
    identity: VerifiedHumanIdentity,
    *,
    status: PrincipalStatus = PrincipalStatus.ACTIVE,
) -> Principal:
    """Flush one exact identity link and its human principal in the caller's transaction."""
    principal = Principal(
        id=PrincipalId(uuid4()),
        organization_id=OrganizationId(uuid4()),
        kind=PrincipalKind.HUMAN,
        status=status,
    )
    session.add(OrganizationRow(id=principal.organization_id.value, name="Identity test"))
    await session.flush()
    session.add(
        PrincipalRow(
            id=principal.id.value,
            organization_id=principal.organization_id.value,
            kind=principal.kind,
            status=principal.status,
            display_name="Test human",
        )
    )
    await session.flush()
    session.add(
        HumanIdentityLinkRow(
            authority=identity.authority.value,
            subject=identity.subject.value,
            organization_id=principal.organization_id.value,
            principal_id=principal.id.value,
            principal_kind=principal.kind,
        )
    )
    await session.flush()
    return principal
