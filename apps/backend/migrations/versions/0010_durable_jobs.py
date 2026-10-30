"""Add bounded ordinary jobs without changing the dedicated recovery queue."""

import sqlalchemy as sa
from alembic import op
from migrations.types import MigrationRevisionReference

revision: str = "0010_durable_jobs"
down_revision: MigrationRevisionReference = "0009_operation_lookup_authority"
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None


def upgrade() -> None:
    op.create_table(
        "application_job_queue", sa.Column("singleton_key", sa.Integer(), primary_key=True)
    )
    op.bulk_insert(
        sa.table("application_job_queue", sa.column("singleton_key", sa.Integer())),
        [{"singleton_key": 1}],
    )
    op.create_table(
        "durable_jobs",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False, primary_key=True),
        sa.Column("operation_id", sa.Text, nullable=False, unique=True),
        sa.Column("request_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("installation_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("principal_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("principal_kind", sa.String(32), nullable=False),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("action_id", sa.String(100), nullable=False),
        sa.Column("payload_kind", sa.String(100), nullable=False),
        sa.Column("payload_version", sa.Integer, nullable=False),
        sa.Column("payload", sa.LargeBinary, nullable=False),
        sa.Column("admitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("queued_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("attempt_count", sa.Integer, nullable=False),
        sa.Column("human_authority", sa.Text, nullable=True),
        sa.Column("human_subject", sa.Text, nullable=True),
        sa.Column("human_version", sa.BigInteger, nullable=True),
        sa.Column("work_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fence", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("worker_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("checkpoint", sa.LargeBinary, nullable=False),
        sa.Column("pending_effect", sa.String(100), nullable=True),
        sa.Column("cancel_requested", sa.Boolean, nullable=False),
        sa.Column("reason", sa.String(100), nullable=True),
        sa.Column("terminal_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_durable_jobs_due", "durable_jobs", ["status", "due_at", "admitted_at", "id"]
    )
    op.create_table(
        "durable_job_attempts",
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("durable_jobs.id"), primary_key=True),
        sa.Column("number", sa.Integer(), primary_key=True),
        sa.Column("fence", sa.Uuid(), nullable=False, unique=True),
        sa.Column("worker_id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.String(100), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("durable_job_attempts")
    op.drop_index("ix_durable_jobs_due", table_name="durable_jobs")
    op.drop_table("durable_jobs")
    op.drop_table("application_job_queue")
