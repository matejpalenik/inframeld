"""Retain one immutable host authorization receipt for audit and replay."""

import sqlalchemy as sa
from alembic import op
from migrations.types import MigrationRevisionReference

revision: str = "0008_host_maintenance_receipts"
down_revision: MigrationRevisionReference = "0007_recovery_cleanup_execution"
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None


def upgrade() -> None:
    op.create_table(
        "host_maintenance_receipts",
        sa.Column("installation_id", sa.Uuid(), primary_key=True),
        sa.Column("operator_request_id", sa.Text(), primary_key=True),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("authority", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("recovery_operation_id", sa.Text(), nullable=False),
        sa.Column("operator_label", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("authorized_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("released", sa.Boolean(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["installation_id"],
            ["installation_identity.installation_id"],
            ondelete="RESTRICT",
            name="fk_maintenance_installation",
        ),
        sa.ForeignKeyConstraint(
            ["recovery_operation_id", "installation_id", "authority", "subject"],
            [
                "identity_recovery_admissions.operation_id",
                "identity_recovery_admissions.installation_id",
                "identity_recovery_admissions.authority",
                "identity_recovery_admissions.subject",
            ],
            ondelete="RESTRICT",
            name="fk_maintenance_recovery",
        ),
        sa.ForeignKeyConstraint(
            ["run_id", "recovery_operation_id"],
            ["identity_recovery_cleanup_runs.id", "identity_recovery_cleanup_runs.operation_id"],
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
            name="fk_maintenance_authorized_run",
        ),
        sa.CheckConstraint(
            sa.column("mode") == "resume-recovery-cleanup", name="ck_maintenance_mode"
        ),
        sa.CheckConstraint(
            sa.and_(
                sa.func.length(sa.func.btrim(sa.column("operator_request_id"))) > 0,
                sa.func.length(sa.column("operator_request_id")) <= 128,
            ),
            name="ck_maintenance_request",
        ),
        sa.CheckConstraint(
            sa.and_(
                sa.func.length(sa.func.btrim(sa.column("operator_label"))) > 0,
                sa.func.length(sa.column("operator_label")) <= 128,
            ),
            name="ck_maintenance_operator",
        ),
        sa.CheckConstraint(
            sa.and_(
                sa.func.length(sa.func.btrim(sa.column("reason"))) > 0,
                sa.func.length(sa.column("reason")) <= 512,
            ),
            name="ck_maintenance_reason",
        ),
        sa.CheckConstraint(
            sa.or_(
                sa.and_(
                    sa.column("outcome") == "cleanup-authorized",
                    sa.column("run_id").is_not(None),
                    sa.column("deadline").is_not(None),
                    sa.column("deadline") > sa.column("authorized_at"),
                    sa.column("released") == sa.false(),
                ),
                sa.and_(
                    sa.column("outcome").in_(("already-completed", "cleanup-confirmed")),
                    sa.column("run_id").is_(None),
                    sa.column("deadline").is_(None),
                    sa.column("released") == (sa.column("outcome") == "already-completed"),
                ),
            ),
            name="ck_maintenance_result",
        ),
        sa.UniqueConstraint("run_id", name="uq_maintenance_new_run"),
    )


def downgrade() -> None:
    op.drop_table("host_maintenance_receipts")
