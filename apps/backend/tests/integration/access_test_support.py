"""Build realistic Access records for PostgreSQL integration tests."""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

TEST_PROJECT_ACTION = "test-project-action"
PrincipalKind = Literal["human", "application"]
PrincipalStatus = Literal["active", "suspended", "retired"]


@dataclass(frozen=True, slots=True)
class ProjectAuthorizationSeed:
    """Identify the principal and project created for an authorization test."""

    principal_id: UUID
    project_id: UUID
    action: str


@dataclass(frozen=True, slots=True)
class MultiProjectAuthorizationSeed:
    """Identify two projects with different grants for the same human principal."""

    principal_id: UUID
    granted_project_id: UUID
    ungranted_project_id: UUID
    action: str


async def seed_project_authorization(
    session: AsyncSession,
    *,
    is_project_member: bool,
    has_action_grant: bool,
    principal_kind: PrincipalKind = "human",
    principal_status: PrincipalStatus = "active",
) -> ProjectAuthorizationSeed:
    """Create a human or application principal with optional project membership and grant."""
    if has_action_grant and not is_project_member:
        raise ValueError("A project action grant requires project membership.")

    organization_id = uuid4()
    principal_id = uuid4()
    project_id = uuid4()

    await session.execute(
        text("INSERT INTO organizations (id, name) VALUES (:id, :name)"),
        {"id": organization_id, "name": "Support"},
    )
    await session.execute(
        text(
            """
            INSERT INTO principals
                (id, organization_id, kind, status, display_name)
            VALUES
                (:id, :organization_id, :kind, :status, :display_name)
            """
        ),
        {
            "id": principal_id,
            "organization_id": organization_id,
            "kind": principal_kind,
            "status": principal_status,
            "display_name": "Alice" if principal_kind == "human" else "SupportBot",
        },
    )
    await session.execute(
        text(
            """
            INSERT INTO projects (id, organization_id, name, status)
            VALUES (:id, :organization_id, 'Support', 'active')
            """
        ),
        {"id": project_id, "organization_id": organization_id},
    )

    if principal_kind == "application":
        await session.execute(
            text(
                """
                INSERT INTO application_accounts
                    (principal_id, organization_id, project_id, principal_kind)
                VALUES (:principal_id, :organization_id, :project_id, 'application')
                """
            ),
            {
                "principal_id": principal_id,
                "organization_id": organization_id,
                "project_id": project_id,
            },
        )

    if is_project_member:
        await session.execute(
            text(
                """
                INSERT INTO project_memberships
                    (
                        project_id,
                        principal_id,
                        organization_id,
                        principal_kind,
                        application_principal_id
                    )
                VALUES
                    (
                        :project_id,
                        :principal_id,
                        :organization_id,
                        :principal_kind,
                        :application_principal_id
                    )
                """
            ),
            {
                "project_id": project_id,
                "principal_id": principal_id,
                "organization_id": organization_id,
                "principal_kind": principal_kind,
                "application_principal_id": (
                    principal_id if principal_kind == "application" else None
                ),
            },
        )

    if has_action_grant:
        await session.execute(
            text(
                """
                INSERT INTO project_action_grants
                    (project_id, recipient_principal_id, recipient_kind, action, can_grant)
                VALUES (:project_id, :principal_id, :principal_kind, :action, false)
                """
            ),
            {
                "project_id": project_id,
                "principal_id": principal_id,
                "principal_kind": principal_kind,
                "action": TEST_PROJECT_ACTION,
            },
        )

    return ProjectAuthorizationSeed(
        principal_id=principal_id,
        project_id=project_id,
        action=TEST_PROJECT_ACTION,
    )


async def seed_multi_project_authorization(
    session: AsyncSession,
) -> MultiProjectAuthorizationSeed:
    """Create Alice as a member of two projects with a grant in only one."""
    organization_id = uuid4()
    principal_id = uuid4()
    granted_project_id = uuid4()
    ungranted_project_id = uuid4()

    await session.execute(
        text("INSERT INTO organizations (id, name) VALUES (:id, :name)"),
        {"id": organization_id, "name": "Support"},
    )
    await session.execute(
        text(
            """
            INSERT INTO principals
                (id, organization_id, kind, status, display_name)
            VALUES (:id, :organization_id, 'human', 'active', 'Alice')
            """
        ),
        {"id": principal_id, "organization_id": organization_id},
    )

    for project_id, project_name in (
        (granted_project_id, "Support"),
        (ungranted_project_id, "Test"),
    ):
        await session.execute(
            text(
                """
                INSERT INTO projects (id, organization_id, name, status)
                VALUES (:id, :organization_id, :name, 'active')
                """
            ),
            {
                "id": project_id,
                "organization_id": organization_id,
                "name": project_name,
            },
        )
        await session.execute(
            text(
                """
                INSERT INTO project_memberships
                    (project_id, principal_id, organization_id, principal_kind)
                VALUES (:project_id, :principal_id, :organization_id, 'human')
                """
            ),
            {
                "project_id": project_id,
                "principal_id": principal_id,
                "organization_id": organization_id,
            },
        )

    await session.execute(
        text(
            """
            INSERT INTO project_action_grants
                (project_id, recipient_principal_id, recipient_kind, action, can_grant)
            VALUES (:project_id, :principal_id, 'human', :action, false)
            """
        ),
        {
            "project_id": granted_project_id,
            "principal_id": principal_id,
            "action": TEST_PROJECT_ACTION,
        },
    )

    return MultiProjectAuthorizationSeed(
        principal_id=principal_id,
        granted_project_id=granted_project_id,
        ungranted_project_id=ungranted_project_id,
        action=TEST_PROJECT_ACTION,
    )
