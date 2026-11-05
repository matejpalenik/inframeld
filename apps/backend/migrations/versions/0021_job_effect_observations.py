"""Retain exact physical invocation identity and non-replayable dispatch admission."""

import sqlalchemy as sa
from alembic import op
from migrations.types import MigrationRevisionReference

revision: str = "0021_job_effect_observations"
down_revision: MigrationRevisionReference = "0020_project_membership"
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None


def upgrade() -> None:
    op.create_table(
        "durable_job_effects",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("durable_jobs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("fence", sa.Uuid(), nullable=False),
        sa.Column("unit", sa.String(100), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("binding_fingerprint", sa.LargeBinary(), nullable=False),
        sa.Column("artifact_id", sa.Uuid(), nullable=False),
        sa.Column(
            "artifact_attempt_id",
            sa.Uuid(),
            sa.ForeignKey("artifact_attempts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("installation_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("work_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("checkpoint", sa.LargeBinary(), nullable=False),
        sa.Column("length", sa.BigInteger(), nullable=True),
        sa.Column("digest", sa.LargeBinary(), nullable=True),
        sa.Column("admitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("aborted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("attempt BETWEEN 1 AND 3", name="ck_job_effect_attempt"),
        sa.CheckConstraint("length(unit) BETWEEN 1 AND 100", name="ck_job_effect_unit"),
        sa.CheckConstraint("action IN ('put', 'delete')", name="ck_job_effect_action"),
        sa.CheckConstraint("octet_length(binding_fingerprint) = 32", name="ck_job_effect_binding"),
        sa.CheckConstraint("octet_length(checkpoint) <= 65536", name="ck_job_effect_checkpoint"),
        sa.CheckConstraint(
            "(length IS NULL AND digest IS NULL AND action = 'delete') OR "
            "(length IS NOT NULL AND length >= 0 AND digest IS NOT NULL AND octet_length(digest) = 32)",
            name="ck_job_effect_sealed_expectation",
        ),
        sa.CheckConstraint(
            "aborted_at IS NULL OR (admitted_at IS NOT NULL AND aborted_at >= admitted_at)",
            name="ck_job_effect_abort_admission",
        ),
        sa.CheckConstraint(
            "consumed_at IS NULL OR (aborted_at IS NOT NULL AND consumed_at >= aborted_at)",
            name="ck_job_effect_consumed_proof",
        ),
    )
    op.create_index(
        "ix_job_effect_pending", "durable_job_effects", ["job_id", "attempt", "fence", "unit"]
    )


def downgrade() -> None:
    op.drop_index("ix_job_effect_pending", table_name="durable_job_effects")
    op.drop_table("durable_job_effects")
