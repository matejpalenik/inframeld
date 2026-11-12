"""Retain original human suspension backing and safe lifecycle receipts."""

from datetime import timedelta

import sqlalchemy as sa
from alembic import op
from migrations.types import MigrationRevisionReference

revision: str = "0034_human_lifecycle"
down_revision: MigrationRevisionReference = "0033_stranded_authority_repair"
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None


def _job_binding_shape(*, suspension: bool) -> sa.ColumnElement[bool]:
    kind = sa.column("binding_kind", sa.String())
    operation = sa.column("operation_id", sa.Text())
    principal = sa.column("principal_id", sa.Uuid())
    principal_kind = sa.column("principal_kind", sa.String())
    action = sa.column("action_id", sa.String())
    project = sa.column("project_id", sa.Uuid())
    artifact_parent = sa.column("cleanup_obligation_id", sa.Uuid())
    deletion_parent = sa.column("deletion_obligation_id", sa.Uuid())
    suspension_parent = sa.column("suspension_obligation_id", sa.Uuid())
    human_unset = sa.and_(
        *(
            sa.column(name).is_(None)
            for name in ("human_authority", "human_subject", "human_version")
        )
    )
    cleanup = sa.and_(
        operation.is_(None),
        principal.is_(None),
        principal_kind.is_(None),
        action.is_(None),
        human_unset,
    )
    old = sa.or_(
        sa.and_(
            kind == "product",
            operation.is_not(None),
            principal.is_not(None),
            principal_kind.is_not(None),
            action.is_not(None),
            artifact_parent.is_(None),
            deletion_parent.is_(None),
        ),
        sa.and_(
            kind == "artifact_cleanup",
            cleanup,
            artifact_parent.is_not(None),
            deletion_parent.is_(None),
        ),
        sa.and_(
            kind == "project_deletion",
            cleanup,
            deletion_parent.is_not(None),
            artifact_parent.is_(None),
        ),
    )
    if not suspension:
        return old
    return sa.or_(
        sa.and_(old, project.is_not(None), suspension_parent.is_(None)),
        sa.and_(
            kind == "human_suspension",
            cleanup,
            project.is_(None),
            suspension_parent.is_not(None),
            artifact_parent.is_(None),
            deletion_parent.is_(None),
        ),
    )


def _maintenance_constraints(*, suspension: bool) -> None:
    table = "host_maintenance_receipts"
    mode, outcome = sa.column("mode"), sa.column("outcome")
    run, deadline, at = sa.column("run_id"), sa.column("deadline"), sa.column("authorized_at")
    recovery, released = sa.column("recovery_operation_id"), sa.column("released")
    no_run = sa.and_(recovery.is_(None), released.is_(None), run.is_(None), deadline.is_(None))
    modes = [
        "resume-recovery-cleanup",
        "repair-stranded-authority",
        "bootstrap-first-administrator",
    ]
    old = sa.or_(
        sa.and_(
            mode == "resume-recovery-cleanup",
            recovery.is_not(None),
            released.is_not(None),
            sa.or_(
                sa.and_(
                    outcome == "cleanup-authorized",
                    run.is_not(None),
                    deadline.is_not(None),
                    deadline > at,
                    released.is_(False),
                ),
                sa.and_(
                    outcome.in_(("already-completed", "cleanup-confirmed")),
                    run.is_(None),
                    deadline.is_(None),
                    released == (outcome == "already-completed"),
                ),
            ),
        ),
        sa.and_(mode == "repair-stranded-authority", outcome == "repaired", no_run),
        sa.and_(mode == "bootstrap-first-administrator", outcome == "bootstrapped", no_run),
    )
    result = old
    if suspension:
        original = sa.column("suspension_obligation_id")
        step = sa.column("suspension_repeat_step")
        attempt = sa.column("suspension_repeat_attempt")
        fence = sa.column("suspension_repeat_fence")
        consumed = sa.column("suspension_repeat_consumed_at")
        no_repeat = sa.and_(step.is_(None), attempt.is_(None), fence.is_(None), consumed.is_(None))
        modes.append("human-suspension-cleanup")
        result = sa.or_(
            sa.and_(old, original.is_(None), no_repeat),
            sa.and_(
                mode == "human-suspension-cleanup",
                original.is_not(None),
                no_run,
                outcome.in_(("requeued", "already-scheduled", "already-complete")),
                sa.or_(
                    no_repeat,
                    sa.and_(
                        outcome == "requeued",
                        step.is_not(None),
                        step.in_(
                            ("kratos_sessions", "hydra_cli_grants", "hydra_remembered_logins")
                        ),
                        attempt.is_not(None),
                        attempt.between(1, 2),
                        fence.is_not(None),
                        sa.or_(consumed.is_(None), consumed >= at),
                    ),
                ),
            ),
        )
    op.drop_constraint("ck_maintenance_mode", table, type_="check")
    op.drop_constraint("ck_maintenance_result", table, type_="check")
    op.create_check_constraint("ck_maintenance_mode", table, mode.in_(modes))
    op.create_check_constraint("ck_maintenance_result", table, result)


def upgrade() -> None:
    admitted = sa.column("admitted_at", sa.DateTime(timezone=True))
    deadline = sa.column("queued_deadline", sa.DateTime(timezone=True))
    exhausted = sa.column("queue_exhausted_at", sa.DateTime(timezone=True))
    completed = sa.column("completed_at", sa.DateTime(timezone=True))
    before = sa.column("before_access_revision", sa.BigInteger())
    after = sa.column("access_revision", sa.BigInteger())
    states = tuple(
        sa.column(name, sa.String())
        for name in ("kratos_sessions", "hydra_cli_grants", "hydra_remembered_logins")
    )
    op.create_table(
        "human_suspension_obligations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("job_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("operation_id", sa.Text(), nullable=False, unique=True),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("installation_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("principal_id", sa.Uuid(), nullable=False),
        sa.Column("initiator_principal_id", sa.Uuid(), nullable=False),
        sa.Column("authority", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column("request_fingerprint", sa.LargeBinary(), nullable=False),
        sa.Column("before_access_revision", sa.BigInteger(), nullable=False),
        sa.Column("access_revision", sa.BigInteger(), nullable=False),
        sa.Column("admitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("queued_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_revision", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("kratos_sessions", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("hydra_cli_grants", sa.String(16), nullable=False, server_default="pending"),
        sa.Column(
            "hydra_remembered_logins", sa.String(16), nullable=False, server_default="pending"
        ),
        sa.Column("queue_exhausted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["installation_id"],
            ["installation_identity.installation_id"],
            name="fk_human_suspension_installation",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "id",
            "installation_id",
            name="uq_human_suspension_maintenance_scope",
        ),
        sa.UniqueConstraint(
            "id",
            "installation_id",
            "organization_id",
            "principal_id",
            name="uq_human_suspension_original_scope",
        ),
        sa.UniqueConstraint(
            "id",
            "job_id",
            "request_id",
            "installation_id",
            "organization_id",
            name="uq_human_suspension_child_scope",
        ),
        sa.CheckConstraint(
            sa.and_(before.between(0, 9007199254740990), after == before + 1),
            name="ck_human_suspension_revisions",
        ),
        sa.CheckConstraint(
            sa.column("source_revision").between(1, 9007199254740991),
            name="ck_human_suspension_source_revision",
        ),
        sa.CheckConstraint(
            sa.and_(
                sa.func.octet_length(sa.column("request_fingerprint")) == 32,
                sa.func.length(sa.func.trim(sa.column("authority"))) > 0,
                sa.func.length(sa.func.trim(sa.column("subject"))) > 0,
                sa.func.length(sa.func.trim(sa.column("request_key"))) > 0,
            ),
            name="ck_human_suspension_original_binding",
        ),
        sa.CheckConstraint(
            sa.and_(
                *(state.in_(("pending", "confirmed", "failed", "uncertain")) for state in states)
            ),
            name="ck_human_suspension_cleanup_states",
        ),
        sa.CheckConstraint(
            sa.and_(
                deadline == admitted + sa.literal(timedelta(hours=24)),
                sa.or_(exhausted.is_(None), sa.and_(exhausted >= deadline, completed.is_(None))),
                sa.or_(
                    completed.is_(None),
                    sa.and_(completed >= admitted, *(state == "confirmed" for state in states)),
                ),
            ),
            name="ck_human_suspension_progress",
        ),
    )
    action = sa.column("action_id", sa.String())
    changed = sa.column("changed", sa.Boolean())
    before_result = sa.column("before_revision", sa.BigInteger())
    after_result = sa.column("access_revision", sa.BigInteger())
    cleanup = sa.column("cleanup_operation_id", sa.Uuid())
    before_version = sa.column("before_credential_version", sa.BigInteger())
    version = sa.column("credential_version", sa.BigInteger())
    delta = sa.case((changed.is_(True), 1), else_=0)
    op.create_table(
        "human_lifecycle_operation_results",
        sa.Column("operation_id", sa.Text(), primary_key=True),
        sa.Column("installation_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("principal_id", sa.Uuid(), nullable=False),
        sa.Column("actor_principal_id", sa.Uuid(), nullable=False),
        sa.Column("action_id", sa.String(32), nullable=False),
        sa.Column("before_revision", sa.BigInteger(), nullable=False),
        sa.Column("access_revision", sa.BigInteger(), nullable=False),
        sa.Column("changed", sa.Boolean(), nullable=False),
        sa.Column("cleanup_operation_id", sa.Uuid(), nullable=True),
        sa.Column("before_credential_version", sa.BigInteger(), nullable=True),
        sa.Column("credential_version", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(
            ["installation_id"],
            ["installation_identity.installation_id"],
            name="fk_human_lifecycle_result_installation",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["operation_id", "organization_id", "actor_principal_id"],
            [
                "idempotency_reservations.operation_id",
                "idempotency_reservations.organization_id",
                "idempotency_reservations.principal_id",
            ],
            name="fk_human_lifecycle_result_operation",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "principal_id"],
            ["principals.organization_id", "principals.id"],
            name="fk_human_lifecycle_result_target",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["cleanup_operation_id", "installation_id", "organization_id", "principal_id"],
            [
                "human_suspension_obligations.id",
                "human_suspension_obligations.installation_id",
                "human_suspension_obligations.organization_id",
                "human_suspension_obligations.principal_id",
            ],
            name="fk_human_lifecycle_result_cleanup",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            sa.and_(
                before_result.between(0, 9007199254740991),
                after_result.between(0, 9007199254740991),
                after_result - before_result == delta,
            ),
            name="ck_human_lifecycle_result_revisions",
        ),
        sa.CheckConstraint(
            sa.or_(
                sa.and_(
                    action == "suspend-users",
                    cleanup.is_not(None),
                    before_version.is_(None),
                    version.is_(None),
                ),
                sa.and_(
                    action == "restore-users",
                    before_version.is_not(None),
                    version.is_not(None),
                    before_version.between(1, 9223372036854775807),
                    version.between(1, 9223372036854775807),
                    version - before_version == delta,
                ),
            ),
            name="ck_human_lifecycle_result_shape",
        ),
    )

    op.add_column("durable_jobs", sa.Column("suspension_obligation_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_job_human_suspension_scope",
        "durable_jobs",
        "human_suspension_obligations",
        ["suspension_obligation_id", "id", "request_id", "installation_id", "organization_id"],
        ["id", "job_id", "request_id", "installation_id", "organization_id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint("ck_job_closed_binding", "durable_jobs", type_="check")
    op.create_check_constraint(
        "ck_job_closed_binding", "durable_jobs", _job_binding_shape(suspension=True)
    )
    op.alter_column("durable_jobs", "project_id", existing_type=sa.Uuid(), nullable=True)

    table = "host_maintenance_receipts"
    op.add_column(table, sa.Column("suspension_obligation_id", sa.Uuid(), nullable=True))
    op.add_column(table, sa.Column("suspension_repeat_step", sa.Text(), nullable=True))
    op.add_column(table, sa.Column("suspension_repeat_attempt", sa.Integer(), nullable=True))
    op.add_column(table, sa.Column("suspension_repeat_fence", sa.Uuid(), nullable=True))
    op.add_column(
        table, sa.Column("suspension_repeat_consumed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_maintenance_suspension_original",
        table,
        "human_suspension_obligations",
        ["suspension_obligation_id", "installation_id"],
        ["id", "installation_id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "uq_maintenance_suspension_repeat",
        table,
        ["suspension_obligation_id"],
        unique=True,
        postgresql_where=sa.column("suspension_repeat_step").is_not(None),
    )
    _maintenance_constraints(suspension=True)


def downgrade() -> None:
    for name in ("human_suspension_obligations", "human_lifecycle_operation_results"):
        if op.get_bind().scalar(sa.select(sa.func.count()).select_from(sa.table(name))):
            raise RuntimeError(
                "Retained human lifecycle backing or originals prevent this downgrade."
            )
    table = "host_maintenance_receipts"
    _maintenance_constraints(suspension=False)
    op.drop_index("uq_maintenance_suspension_repeat", table_name=table)
    op.drop_constraint("fk_maintenance_suspension_original", table, type_="foreignkey")
    for column in (
        "suspension_repeat_consumed_at",
        "suspension_repeat_fence",
        "suspension_repeat_attempt",
        "suspension_repeat_step",
        "suspension_obligation_id",
    ):
        op.drop_column(table, column)
    op.alter_column("durable_jobs", "project_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_constraint("ck_job_closed_binding", "durable_jobs", type_="check")
    op.create_check_constraint(
        "ck_job_closed_binding", "durable_jobs", _job_binding_shape(suspension=False)
    )
    op.drop_constraint("fk_job_human_suspension_scope", "durable_jobs", type_="foreignkey")
    op.drop_column("durable_jobs", "suspension_obligation_id")
    op.drop_table("human_lifecycle_operation_results")
    op.drop_table("human_suspension_obligations")
