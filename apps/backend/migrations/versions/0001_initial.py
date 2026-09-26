"""Create the initial relational schema for Access."""

import sqlalchemy as sa
from alembic import op
from migrations.types import MigrationRevisionReference
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: MigrationRevisionReference = None
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None


def upgrade() -> None:
    """Create the shared identity, membership, grant, and audit tables."""
    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("access_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("access_revision >= 0", name="ck_organizations_revision_nonnegative"),
    )

    op.create_table(
        "principals",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_principals_org_id"),
        sa.UniqueConstraint("organization_id", "id", "kind", name="uq_principals_org_id_kind"),
        sa.CheckConstraint("kind IN ('human', 'application')", name="ck_principals_kind"),
        sa.CheckConstraint(
            "status IN ('active', 'suspended', 'retired')", name="ck_principals_status"
        ),
    )

    op.create_table(
        "human_identity_links",
        sa.Column("authority", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("principal_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("principal_kind", sa.String(length=20), nullable=False),
        sa.Column(
            "linked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("authority", "subject", name="pk_human_identity_links"),
        sa.ForeignKeyConstraint(
            ["organization_id", "principal_id", "principal_kind"],
            ["principals.organization_id", "principals.id", "principals.kind"],
            name="fk_identity_links_human_principal",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("principal_kind = 'human'", name="ck_identity_links_human_only"),
        sa.CheckConstraint(
            "length(trim(authority)) > 0 AND length(trim(subject)) > 0",
            name="ck_identity_links_nonempty_identity",
        ),
    )

    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("access_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_projects_org_id"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_projects_organization",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("status IN ('active', 'deleting')", name="ck_projects_status"),
        sa.CheckConstraint("access_revision >= 0", name="ck_projects_revision_nonnegative"),
    )

    op.create_table(
        "application_accounts",
        sa.Column("principal_id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("principal_kind", sa.String(length=20), nullable=False),
        sa.UniqueConstraint("project_id", "principal_id", name="uq_application_accounts_project"),
        sa.ForeignKeyConstraint(
            ["organization_id", "principal_id", "principal_kind"],
            ["principals.organization_id", "principals.id", "principals.kind"],
            name="fk_application_accounts_application_principal",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id"],
            ["projects.organization_id", "projects.id"],
            name="fk_application_accounts_project",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("principal_kind = 'application'", name="ck_application_accounts_kind"),
    )

    op.create_table(
        "project_memberships",
        sa.Column("project_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("principal_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("principal_kind", sa.String(length=20), nullable=False),
        sa.Column("application_principal_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "assigned_by_principal_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("principals.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("project_id", "principal_id", name="pk_project_memberships"),
        sa.UniqueConstraint(
            "project_id", "principal_id", "principal_kind", name="uq_project_memberships_kind"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id"],
            ["projects.organization_id", "projects.id"],
            name="fk_project_memberships_project",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "principal_id", "principal_kind"],
            ["principals.organization_id", "principals.id", "principals.kind"],
            name="fk_project_memberships_principal",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "application_principal_id"],
            ["application_accounts.project_id", "application_accounts.principal_id"],
            name="fk_project_memberships_application_account",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "(principal_kind = 'human' AND application_principal_id IS NULL) OR "
            "(principal_kind = 'application' AND application_principal_id = principal_id)",
            name="ck_project_memberships_application_binding",
        ),
    )

    op.create_table(
        "access_groups",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("project_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("project_id", "id", name="uq_access_groups_project_id"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_access_groups_project",
            ondelete="RESTRICT",
        ),
    )

    op.create_table(
        "group_memberships",
        sa.Column("project_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("group_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("principal_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "assigned_by_principal_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("principals.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint(
            "project_id", "group_id", "principal_id", name="pk_group_memberships"
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "group_id"],
            ["access_groups.project_id", "access_groups.id"],
            name="fk_group_memberships_group",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "principal_id"],
            ["project_memberships.project_id", "project_memberships.principal_id"],
            name="fk_group_memberships_project_member",
            ondelete="RESTRICT",
        ),
    )

    op.create_table(
        "group_managers",
        sa.Column("project_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("group_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("principal_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("principal_kind", sa.String(length=20), nullable=False),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "assigned_by_principal_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("principals.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("project_id", "group_id", "principal_id", name="pk_group_managers"),
        sa.ForeignKeyConstraint(
            ["project_id", "group_id"],
            ["access_groups.project_id", "access_groups.id"],
            name="fk_group_managers_group",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "principal_id", "principal_kind"],
            [
                "project_memberships.project_id",
                "project_memberships.principal_id",
                "project_memberships.principal_kind",
            ],
            name="fk_group_managers_project_member",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "group_id", "principal_id"],
            [
                "group_memberships.project_id",
                "group_memberships.group_id",
                "group_memberships.principal_id",
            ],
            name="fk_group_managers_group_member",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("principal_kind = 'human'", name="ck_group_managers_human_only"),
    )

    op.create_table(
        "organization_action_grants",
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("recipient_principal_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("recipient_kind", sa.String(length=20), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("can_grant", sa.Boolean(), nullable=False),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "assigned_by_principal_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("principals.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint(
            "organization_id", "recipient_principal_id", "action", name="pk_org_action_grants"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_org_action_grants_organization",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "recipient_principal_id", "recipient_kind"],
            ["principals.organization_id", "principals.id", "principals.kind"],
            name="fk_org_action_grants_recipient",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("recipient_kind = 'human'", name="ck_org_action_grants_human_only"),
        sa.CheckConstraint("length(trim(action)) > 0", name="ck_org_action_grants_action_nonempty"),
    )

    op.create_table(
        "project_action_grants",
        sa.Column("project_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("recipient_principal_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("recipient_kind", sa.String(length=20), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("can_grant", sa.Boolean(), nullable=False),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "assigned_by_principal_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("principals.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint(
            "project_id", "recipient_principal_id", "action", name="pk_project_action_grants"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_project_action_grants_project",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "recipient_principal_id", "recipient_kind"],
            [
                "project_memberships.project_id",
                "project_memberships.principal_id",
                "project_memberships.principal_kind",
            ],
            name="fk_project_action_grants_recipient",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "recipient_kind IN ('human', 'application')",
            name="ck_project_action_grants_recipient_kind",
        ),
        sa.CheckConstraint(
            "recipient_kind = 'human' OR can_grant = false",
            name="ck_project_action_grants_application_use_only",
        ),
        sa.CheckConstraint(
            "length(trim(action)) > 0", name="ck_project_action_grants_action_nonempty"
        ),
    )

    op.create_table(
        "group_action_grants",
        sa.Column("project_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("group_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("recipient_principal_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("recipient_kind", sa.String(length=20), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("can_grant", sa.Boolean(), nullable=False),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "assigned_by_principal_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("principals.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint(
            "project_id",
            "group_id",
            "recipient_principal_id",
            "action",
            name="pk_group_action_grants",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "group_id"],
            ["access_groups.project_id", "access_groups.id"],
            name="fk_group_action_grants_group",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "recipient_principal_id", "recipient_kind"],
            [
                "project_memberships.project_id",
                "project_memberships.principal_id",
                "project_memberships.principal_kind",
            ],
            name="fk_group_action_grants_recipient",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "recipient_kind IN ('human', 'application')",
            name="ck_group_action_grants_recipient_kind",
        ),
        sa.CheckConstraint(
            "recipient_kind = 'human' OR can_grant = false",
            name="ck_group_action_grants_application_use_only",
        ),
        sa.CheckConstraint(
            "length(trim(action)) > 0", name="ck_group_action_grants_action_nonempty"
        ),
    )

    op.create_table(
        "application_action_grants",
        sa.Column("project_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("application_principal_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("recipient_principal_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("recipient_kind", sa.String(length=20), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("can_grant", sa.Boolean(), nullable=False),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "assigned_by_principal_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("principals.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint(
            "project_id",
            "application_principal_id",
            "recipient_principal_id",
            "action",
            name="pk_application_action_grants",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "application_principal_id"],
            ["application_accounts.project_id", "application_accounts.principal_id"],
            name="fk_application_action_grants_application",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "recipient_principal_id", "recipient_kind"],
            [
                "project_memberships.project_id",
                "project_memberships.principal_id",
                "project_memberships.principal_kind",
            ],
            name="fk_application_action_grants_recipient",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "recipient_kind = 'human'", name="ck_application_action_grants_human_only"
        ),
        sa.CheckConstraint(
            "length(trim(action)) > 0", name="ck_application_action_grants_action_nonempty"
        ),
    )

    op.create_table(
        "access_audit_events",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "organization_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("project_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("actor_kind", sa.String(length=32), nullable=False),
        sa.Column(
            "actor_principal_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("principals.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("actor_reference", sa.Text(), nullable=True),
        sa.Column(
            "affected_principal_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("principals.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("target_kind", sa.String(length=100), nullable=False),
        sa.Column("target_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=True),
        sa.Column("before_values", postgresql.JSONB(), nullable=True),
        sa.Column("after_values", postgresql.JSONB(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "length(trim(actor_kind)) > 0", name="ck_access_audit_actor_kind_nonempty"
        ),
        sa.CheckConstraint(
            "length(trim(event_type)) > 0", name="ck_access_audit_event_type_nonempty"
        ),
        sa.CheckConstraint(
            "length(trim(target_kind)) > 0", name="ck_access_audit_target_kind_nonempty"
        ),
    )


def downgrade() -> None:
    """Remove the Access tables in dependency order."""
    op.drop_table("access_audit_events")
    op.drop_table("application_action_grants")
    op.drop_table("group_action_grants")
    op.drop_table("project_action_grants")
    op.drop_table("organization_action_grants")
    op.drop_table("group_managers")
    op.drop_table("group_memberships")
    op.drop_table("access_groups")
    op.drop_table("project_memberships")
    op.drop_table("application_accounts")
    op.drop_table("human_identity_links")
    op.drop_table("projects")
    op.drop_table("principals")
    op.drop_table("organizations")
