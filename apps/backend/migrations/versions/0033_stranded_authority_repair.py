"""Retain exact broader-repair originals independently of mutable Access assignments."""

import sqlalchemy as sa
from alembic import op
from migrations.types import MigrationRevisionReference

revision: str = "0033_stranded_authority_repair"
down_revision: MigrationRevisionReference = "0032_application_retirement"
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None


def upgrade() -> None:
    kind, target = sa.column("responsibility_kind"), sa.column("target_kind")
    project, group, account = (
        sa.column("project_id"),
        sa.column("access_group_id"),
        sa.column("application_account_id"),
    )
    action = sa.column("action_id")
    before, after = (
        sa.column("before_revision", sa.BigInteger()),
        sa.column("after_revision", sa.BigInteger()),
    )
    project_actions = (
        "manage-project-members",
        "create-access-groups",
        "create-application-accounts",
        "create-pipelines",
        "create-deployments",
        "manage-upload-defaults",
        "delete-project",
        "inspect-budget",
        "manage-budget",
        "manage-trace-policy",
        "delete-trace-history",
        "inspect-feedback",
        "create-collections",
        "create-sources",
        "create-model-connections",
        "create-processing-profiles",
        "create-embedding-profiles",
    )
    op.create_table(
        "stranded_authority_repair_receipts",
        sa.Column("installation_id", sa.Uuid(), primary_key=True),
        sa.Column("operator_request_id", sa.Text(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_id", sa.Uuid(), nullable=False),
        sa.Column("expected_identity_id", sa.Uuid(), nullable=False),
        sa.Column("request_fingerprint", sa.LargeBinary(), nullable=False),
        sa.Column("before_revision", sa.BigInteger(), nullable=False),
        sa.Column("after_revision", sa.BigInteger(), nullable=False),
        sa.Column("responsibility_kind", sa.String(32), nullable=False),
        sa.Column("target_kind", sa.String(32), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("access_group_id", sa.Uuid(), nullable=True),
        sa.Column("application_account_id", sa.Uuid(), nullable=True),
        sa.Column("action_id", sa.String(100), nullable=True),
        sa.ForeignKeyConstraint(
            ["installation_id", "operator_request_id"],
            [
                "host_maintenance_receipts.installation_id",
                "host_maintenance_receipts.operator_request_id",
            ],
            name="fk_stranded_repair_host_original",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            sa.and_(
                before.between(0, 9007199254740990),
                after.between(1, 9007199254740991),
                after == before + 1,
            ),
            name="ck_stranded_repair_revisions",
        ),
        sa.CheckConstraint(
            sa.func.octet_length(sa.column("request_fingerprint")) == 32,
            name="ck_stranded_repair_fingerprint",
        ),
        sa.CheckConstraint(
            sa.or_(
                sa.and_(
                    kind == "group-manager",
                    target == "access-group",
                    project.is_not(None),
                    group.is_not(None),
                    account.is_(None),
                    action.is_(None),
                ),
                sa.and_(
                    kind == "action-grantor",
                    action.is_not(None),
                    sa.or_(
                        sa.and_(
                            target == "organization",
                            project.is_(None),
                            group.is_(None),
                            account.is_(None),
                            action.in_(
                                ("admit-users", "suspend-users", "restore-users", "create-projects")
                            ),
                        ),
                        sa.and_(
                            target == "project",
                            project.is_not(None),
                            group.is_(None),
                            account.is_(None),
                            action.in_(project_actions),
                        ),
                        sa.and_(
                            target == "access-group",
                            project.is_not(None),
                            group.is_not(None),
                            account.is_(None),
                            action.in_(("add-documents", "update-documents", "delete-documents")),
                        ),
                        sa.and_(
                            target == "application-account",
                            project.is_not(None),
                            group.is_(None),
                            account.is_not(None),
                            action.in_(
                                (
                                    "issue-application-keys",
                                    "revoke-application-keys",
                                    "delete-application-account",
                                )
                            ),
                        ),
                    ),
                ),
            ),
            name="ck_stranded_repair_responsibility",
        ),
    )


def downgrade() -> None:
    broader = sa.table("stranded_authority_repair_receipts", sa.column("installation_id"))
    parent = sa.table(
        "host_maintenance_receipts",
        sa.column("installation_id"),
        sa.column("operator_request_id"),
        sa.column("mode"),
    )
    legacy = sa.table(
        "project_metadata_repair_receipts",
        sa.column("installation_id"),
        sa.column("operator_request_id"),
    )
    has_legacy = sa.exists().where(
        legacy.c.installation_id == parent.c.installation_id,
        legacy.c.operator_request_id == parent.c.operator_request_id,
    )
    if op.get_bind().scalar(
        sa.select(sa.func.count()).select_from(broader)
    ) or op.get_bind().scalar(
        sa.select(sa.func.count())
        .select_from(parent)
        .where(parent.c.mode == "repair-stranded-authority", ~has_legacy)
    ):
        raise RuntimeError("Retained stranded-authority repair originals prevent this downgrade.")
    op.drop_table("stranded_authority_repair_receipts")
