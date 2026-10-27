"""Persist fenced recovery attempts and complete cleanup provenance."""

import sqlalchemy as sa
from alembic import op
from migrations.types import MigrationRevisionReference

# Keep the revision within Alembic's existing VARCHAR(32) metadata contract.
revision: str = "0007_recovery_cleanup_execution"
down_revision: MigrationRevisionReference = "0006_identity_recovery_delivery"
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None


def upgrade() -> None:
    op.add_column(
        "identity_recovery_proof_links",
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint(
        "uq_recovery_run_operation", "identity_recovery_cleanup_runs", ["id", "operation_id"]
    )
    op.create_table(
        "identity_recovery_cleanup_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("operation_id", sa.Text(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.Uuid(), nullable=False),
        sa.Column("ownership_token", sa.Uuid(), nullable=False, unique=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("terminal_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id", "operation_id"],
            ["identity_recovery_cleanup_runs.id", "identity_recovery_cleanup_runs.operation_id"],
            ondelete="RESTRICT",
            name="fk_recovery_attempt_run",
        ),
        sa.UniqueConstraint("run_id", "ordinal", name="uq_recovery_attempt_ordinal"),
        sa.UniqueConstraint("id", "operation_id", name="uq_recovery_attempt_operation"),
        sa.CheckConstraint(
            sa.and_(sa.column("ordinal") >= 1, sa.column("ordinal") <= 12),
            name="ck_recovery_attempt_ordinal",
        ),
        sa.CheckConstraint(
            sa.column("lease_expires_at") > sa.column("claimed_at"),
            name="ck_recovery_attempt_lease",
        ),
        sa.CheckConstraint(
            sa.column("ended_at").is_(None) == sa.column("terminal_reason").is_(None),
            name="ck_recovery_attempt_terminal",
        ),
    )
    op.create_table(
        "identity_recovery_cleanup_steps",
        sa.Column("attempt_id", sa.Uuid(), primary_key=True),
        sa.Column("step", sa.Text(), primary_key=True),
        sa.Column("operation_id", sa.Text(), nullable=False),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("checkpointed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("state", sa.Text(), nullable=True),
        sa.Column("disposition", sa.Text(), nullable=True),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("retry_after_seconds", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(
            ["attempt_id", "operation_id"],
            [
                "identity_recovery_cleanup_attempts.id",
                "identity_recovery_cleanup_attempts.operation_id",
            ],
            ondelete="RESTRICT",
            name="fk_recovery_step_attempt",
        ),
        sa.CheckConstraint(
            sa.column("step").in_(("cli-grants", "remembered-logins")), name="ck_recovery_step_name"
        ),
        sa.CheckConstraint(
            sa.or_(
                sa.and_(
                    *[
                        sa.column(c).is_(None)
                        for c in (
                            "checkpointed_at",
                            "state",
                            "disposition",
                            "category",
                            "http_status",
                            "retry_after_seconds",
                        )
                    ]
                ),
                sa.and_(
                    sa.column("checkpointed_at").is_not(None),
                    sa.column("state").is_not(None),
                    sa.column("disposition").is_not(None),
                    sa.column("category").is_not(None),
                    sa.column("state").in_(("confirmed", "failed", "uncertain")),
                    sa.column("disposition").in_(("not_needed", "retryable", "operator_required")),
                    (sa.column("state") == "confirmed")
                    == (sa.column("disposition") == "not_needed"),
                ),
            ),
            name="ck_recovery_step_observation",
        ),
        sa.CheckConstraint(
            sa.column("category").is_(None)
            | sa.column("category").in_(
                (
                    "acknowledged",
                    "rate_limited",
                    "transport_failure",
                    "provider_timeout",
                    "provider_rejection",
                    "provider_unavailable",
                    "provider_protocol_error",
                )
            ),
            name="ck_recovery_step_category",
        ),
        sa.CheckConstraint(
            sa.column("http_status").is_(None) | sa.column("http_status").between(100, 599),
            name="ck_recovery_step_status",
        ),
        sa.CheckConstraint(
            sa.column("retry_after_seconds").is_(None)
            | sa.and_(
                sa.column("retry_after_seconds") >= 0,
                sa.column("retry_after_seconds") < sa.cast(sa.literal("Infinity"), sa.Float()),
            ),
            name="ck_recovery_step_delay",
        ),
    )
    job = "identity_recovery_cleanup_jobs"
    for name in (
        "worker_id",
        "ownership_token",
        "active_attempt_id",
        "cli_confirmation_attempt_id",
        "login_confirmation_attempt_id",
    ):
        op.add_column(job, sa.Column(name, sa.Uuid(), nullable=True))
    op.add_column(job, sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    lease_columns = ("worker_id", "ownership_token", "active_attempt_id", "lease_expires_at")
    op.create_check_constraint(
        "ck_recovery_job_ownership",
        job,
        sa.or_(
            sa.and_(*[sa.column(c).is_(None) for c in lease_columns]),
            sa.and_(*[sa.column(c).is_not(None) for c in lease_columns]),
        ),
    )
    for column in (
        "active_attempt_id",
        "cli_confirmation_attempt_id",
        "login_confirmation_attempt_id",
    ):
        op.create_foreign_key(
            "fk_recovery_job_" + column,
            job,
            "identity_recovery_cleanup_attempts",
            [column, "operation_id"],
            ["id", "operation_id"],
            ondelete="RESTRICT",
        )
    op.create_table(
        "identity_recovery_cleanup_proofs",
        sa.Column("operation_id", sa.Text(), primary_key=True),
        sa.Column("installation_id", sa.Uuid(), nullable=False),
        sa.Column("authority", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("source_operation_id", sa.Text(), nullable=False),
        sa.Column("source_receipt_id", sa.Uuid(), nullable=False),
        sa.Column("cli_confirmation_attempt_id", sa.Uuid(), nullable=False),
        sa.Column("login_confirmation_attempt_id", sa.Uuid(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reconcile_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("propagation_complete", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("release_status", sa.Text(), nullable=True),
        *[
            sa.ForeignKeyConstraint(
                [c, "installation_id", "authority", "subject"],
                [
                    "identity_recovery_admissions." + f
                    for f in ("operation_id", "installation_id", "authority", "subject")
                ],
                ondelete="RESTRICT",
                name="fk_recovery_proof_" + c,
            )
            for c in ("operation_id", "source_operation_id")
        ],
        sa.ForeignKeyConstraint(
            ["source_receipt_id", "source_operation_id"],
            [
                "identity_recovery_evidence_receipts.id",
                "identity_recovery_evidence_receipts.operation_id",
            ],
            ondelete="RESTRICT",
            name="fk_recovery_complete_receipt",
        ),
        *[
            sa.ForeignKeyConstraint(
                [c, "source_operation_id"],
                [
                    "identity_recovery_cleanup_attempts.id",
                    "identity_recovery_cleanup_attempts.operation_id",
                ],
                ondelete="RESTRICT",
                name="fk_recovery_proof_" + c,
            )
            for c in ("cli_confirmation_attempt_id", "login_confirmation_attempt_id")
        ],
        sa.CheckConstraint(
            sa.or_(
                sa.and_(sa.column("checked_at").is_(None), sa.column("release_status").is_(None)),
                sa.and_(
                    sa.column("checked_at").is_not(None),
                    sa.column("release_status").is_not(None),
                    sa.column("release_status").in_(("released", "ineligible")),
                ),
            ),
            name="ck_recovery_proof_release",
        ),
    )
    op.create_index(
        "ix_recovery_due_run",
        "identity_recovery_cleanup_runs",
        ["next_attempt_at", "operation_id"],
        postgresql_where=sa.column("ended_at").is_(None),
    )
    op.create_index(
        "ix_recovery_pending_proof",
        "identity_recovery_cleanup_proofs",
        ["reconcile_at", "operation_id"],
        postgresql_where=sa.or_(
            sa.column("checked_at").is_(None), sa.column("propagation_complete") == sa.false()
        ),
    )


def downgrade() -> None:
    raise RuntimeError("Downgrading recovery execution history is unsupported.")
