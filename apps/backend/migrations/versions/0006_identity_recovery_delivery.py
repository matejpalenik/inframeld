"""Persist trusted native evidence and the original recovery cleanup handoff."""

import sqlalchemy as sa
from alembic import op
from migrations.types import MigrationRevisionReference

revision: str = "0006_identity_recovery_delivery"
down_revision: MigrationRevisionReference = "0005_human_credential_versions"
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None


def _scope() -> list[sa.Column[object]]:
    return [
        sa.Column("installation_id", sa.Uuid(), nullable=False),
        sa.Column("authority", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("operation_id", sa.Text(), nullable=False),
    ]


def _admission_fk(name: str) -> sa.ForeignKeyConstraint:
    columns = ["operation_id", "installation_id", "authority", "subject"]
    return sa.ForeignKeyConstraint(
        columns,
        [f"identity_recovery_admissions.{c}" for c in columns],
        name=name,
        ondelete="RESTRICT",
    )


def _recorded() -> sa.Column[object]:
    return sa.Column(
        "recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_recovery_admission_binding",
        "identity_recovery_admissions",
        ["operation_id", "installation_id", "authority", "subject"],
    )
    op.create_table(
        "identity_recovery_session_bindings",
        *_scope(),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        _recorded(),
        sa.PrimaryKeyConstraint("installation_id", "authority", "session_id"),
        sa.UniqueConstraint(
            "installation_id",
            "authority",
            "subject",
            "session_id",
            "operation_id",
            name="uq_recovery_session_binding",
        ),
        _admission_fk("fk_recovery_session_admission"),
    )
    op.create_table(
        "identity_recovery_settings_bindings",
        *_scope(),
        sa.Column("settings_flow_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("source_recovery_flow_id", sa.Uuid(), nullable=True),
        _recorded(),
        sa.PrimaryKeyConstraint("installation_id", "authority", "settings_flow_id"),
        _admission_fk("fk_recovery_settings_admission"),
        sa.ForeignKeyConstraint(
            ["installation_id", "authority", "subject", "session_id", "operation_id"],
            [
                f"identity_recovery_session_bindings.{c}"
                for c in ["installation_id", "authority", "subject", "session_id", "operation_id"]
            ],
            name="fk_recovery_settings_session",
            ondelete="RESTRICT",
        ),
    )
    op.create_table(
        "identity_recovery_evidence_receipts",
        *_scope(),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("native_flow_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("source_recovery_flow_id", sa.Uuid(), nullable=True),
        sa.Column("event_kind", sa.Text(), nullable=True),
        _recorded(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "installation_id",
            "authority",
            "event_type",
            "native_flow_id",
            name="uq_recovery_evidence_event",
        ),
        sa.UniqueConstraint("id", "operation_id", name="uq_recovery_evidence_operation"),
        _admission_fk("fk_recovery_evidence_admission"),
        sa.CheckConstraint(
            sa.or_(
                sa.and_(
                    sa.column("event_type") == "recovery-code-verified",
                    sa.column("event_kind").is_not(None),
                    sa.column("event_kind").in_(("recovery", "password-reset")),
                    sa.column("session_id").is_(None),
                    sa.column("source_recovery_flow_id").is_(None),
                ),
                sa.and_(
                    sa.column("event_type").in_(
                        ("settings-flow-associated", "password-settings-saved")
                    ),
                    sa.column("event_kind").is_(None),
                    sa.column("session_id").is_not(None),
                ),
            ),
            name="ck_recovery_evidence_shape",
        ),
    )
    op.create_table(
        "identity_recovery_proof_links",
        sa.Column("installation_id", sa.Uuid(), nullable=False),
        sa.Column("authority", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("covering_operation_id", sa.Text(), nullable=False),
        sa.Column("covered_operation_id", sa.Text(), nullable=False),
        _recorded(),
        sa.PrimaryKeyConstraint("covering_operation_id", "covered_operation_id"),
        *[
            sa.ForeignKeyConstraint(
                [f"{side}_operation_id", "installation_id", "authority", "subject"],
                [
                    f"identity_recovery_admissions.{c}"
                    for c in ["operation_id", "installation_id", "authority", "subject"]
                ],
                name=f"fk_recovery_proof_{side}",
                ondelete="RESTRICT",
            )
            for side in ("covering", "covered")
        ],
        sa.CheckConstraint(
            sa.column("covering_operation_id") != sa.column("covered_operation_id"),
            name="ck_recovery_proof_distinct",
        ),
    )
    op.create_table(
        "identity_recovery_cleanup_jobs",
        *_scope(),
        sa.Column("evidence_receipt_id", sa.Uuid(), nullable=False),
        sa.Column("eligible_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cli_grants_state", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("remembered_logins_state", sa.Text(), nullable=False, server_default="pending"),
        sa.PrimaryKeyConstraint("operation_id"),
        _admission_fk("fk_recovery_job_admission"),
        sa.ForeignKeyConstraint(
            ["evidence_receipt_id", "operation_id"],
            [
                "identity_recovery_evidence_receipts.id",
                "identity_recovery_evidence_receipts.operation_id",
            ],
            name="fk_recovery_job_evidence",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            sa.and_(
                *[
                    sa.column(c).in_(("pending", "confirmed", "failed", "uncertain"))
                    for c in ("cli_grants_state", "remembered_logins_state")
                ]
            ),
            name="ck_recovery_job_states",
        ),
    )
    op.create_table(
        "identity_recovery_cleanup_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("operation_id", sa.Text(), nullable=False),
        sa.Column("authorization_source", sa.Text(), nullable=False),
        sa.Column("authorized_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="12"),
        sa.Column("consumed_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("terminal_reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["operation_id"],
            ["identity_recovery_cleanup_jobs.operation_id"],
            name="fk_recovery_run_job",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            sa.and_(
                sa.column("max_attempts") == 12,
                sa.column("consumed_attempts") >= 0,
                sa.column("consumed_attempts") <= sa.column("max_attempts"),
            ),
            name="ck_recovery_run_budget",
        ),
        sa.CheckConstraint(
            sa.and_(
                sa.column("deadline") > sa.column("authorized_at"),
                sa.column("next_attempt_at") >= sa.column("authorized_at"),
                sa.column("next_attempt_at") <= sa.column("deadline"),
            ),
            name="ck_recovery_run_times",
        ),
        sa.CheckConstraint(
            sa.column("authorization_source").in_(("kratos-evidence", "host-operator")),
            name="ck_recovery_run_source",
        ),
        sa.CheckConstraint(
            sa.column("ended_at").is_(None) == sa.column("terminal_reason").is_(None),
            name="ck_recovery_run_terminal",
        ),
    )
    op.create_index(
        "uq_recovery_active_run",
        "identity_recovery_cleanup_runs",
        ["operation_id"],
        unique=True,
        postgresql_where=sa.column("ended_at").is_(None),
    )


def downgrade() -> None:
    raise RuntimeError("Downgrading recovery delivery evidence is unsupported.")
