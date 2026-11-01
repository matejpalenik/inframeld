"""Retain content-free deletion status independently of removed product records."""

import sqlalchemy as sa
from alembic import op
from migrations.types import MigrationRevisionReference

revision: str = "0013_deletion_status"
down_revision: MigrationRevisionReference = "0010_durable_jobs"
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None


def upgrade() -> None:
    op.create_table(
        "deletion_status_bindings",
        sa.Column("operation_id", sa.Text(), primary_key=True),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("installation_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("initiator_principal_id", sa.Uuid(), nullable=False),
        sa.Column("method", sa.String(16), nullable=False),
        sa.Column("requested_route", sa.Text(), nullable=False),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column("request_fingerprint", sa.LargeBinary(), nullable=False),
        sa.Column("authority_family", sa.String(32), nullable=False),
        sa.Column("action_id", sa.String(100), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.clock_timestamp(),
        ),
        sa.Column("retention_days", sa.Integer(), nullable=False),
        sa.Column("retention_policy_version", sa.String(64), nullable=False),
        sa.CheckConstraint("retention_days BETWEEN 1 AND 90", name="ck_deletion_status_retention"),
        sa.CheckConstraint(
            "octet_length(request_fingerprint) = 32", name="ck_deletion_status_fingerprint"
        ),
    )
    op.create_table(
        "deletion_status_observations",
        sa.Column(
            "operation_id",
            sa.Text(),
            sa.ForeignKey("deletion_status_bindings.operation_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("owner_revision", sa.BigInteger(), nullable=False),
        sa.Column(
            "owner_observed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.clock_timestamp(),
        ),
        sa.Column("job_status", sa.String(32), nullable=True),
        sa.Column("admission_confirmed", sa.Boolean(), nullable=True),
        sa.Column("access_blocked", sa.Boolean(), nullable=True),
        sa.Column("application_shutdown_complete", sa.Boolean(), nullable=True),
        sa.Column("physical_cleanup_complete", sa.Boolean(), nullable=True),
        sa.Column("unfinished_obligation_id", sa.Uuid(), nullable=True),
        sa.Column("unfinished_operation_id", sa.Text(), nullable=True),
        sa.Column("unfinished_installation_id", sa.Uuid(), nullable=True),
        sa.Column("unfinished_organization_id", sa.Uuid(), nullable=True),
        sa.Column("unfinished_project_id", sa.Uuid(), nullable=True),
        sa.Column("unfinished_initiator_principal_id", sa.Uuid(), nullable=True),
        sa.Column("unfinished_observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unfinished_source_revision", sa.BigInteger(), nullable=True),
        sa.Column("retention_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("owner_revision > 0", name="ck_deletion_status_owner_revision"),
    )


def downgrade() -> None:
    op.drop_table("deletion_status_observations")
    op.drop_table("deletion_status_bindings")
