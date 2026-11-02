"""Retain one installation claim without changing existing maintenance outcomes."""

import sqlalchemy as sa
from alembic import op
from migrations.types import MigrationRevisionReference

revision: str = "0016_first_administrator"
down_revision: MigrationRevisionReference = "0015_artifact_allocation"
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None


def _maintenance_constraints(*, bootstrap: bool) -> None:
    mode, outcome = sa.column("mode"), sa.column("outcome")
    run, deadline, at = sa.column("run_id"), sa.column("deadline"), sa.column("authorized_at")
    recovery, released = sa.column("recovery_operation_id"), sa.column("released")
    modes = ["resume-recovery-cleanup", "repair-stranded-authority"]
    results = [
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
        sa.and_(
            mode == "repair-stranded-authority",
            outcome == "repaired",
            recovery.is_(None),
            released.is_(None),
            run.is_(None),
            deadline.is_(None),
        ),
    ]
    if bootstrap:
        modes.append("bootstrap-first-administrator")
        results.append(
            sa.and_(
                mode == "bootstrap-first-administrator",
                outcome == "bootstrapped",
                recovery.is_(None),
                released.is_(None),
                run.is_(None),
                deadline.is_(None),
            )
        )
    op.create_check_constraint("ck_maintenance_mode", "host_maintenance_receipts", mode.in_(modes))
    op.create_check_constraint(
        "ck_maintenance_result", "host_maintenance_receipts", sa.or_(*results)
    )


def upgrade() -> None:
    op.drop_constraint("ck_maintenance_mode", "host_maintenance_receipts", type_="check")
    op.drop_constraint("ck_maintenance_result", "host_maintenance_receipts", type_="check")
    _maintenance_constraints(bootstrap=True)
    op.create_table(
        "first_administrator_bootstrap_receipts",
        sa.Column("installation_id", sa.Uuid(), primary_key=True),
        sa.Column("operator_request_id", sa.Text(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("organization_name", sa.Text(), nullable=False),
        sa.Column("recipient_id", sa.Uuid(), nullable=False),
        sa.Column("expected_identity_id", sa.Uuid(), nullable=False),
        sa.Column("request_fingerprint", sa.LargeBinary(), nullable=False),
        sa.Column("before_revision", sa.BigInteger(), nullable=False),
        sa.Column("after_revision", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["installation_id", "operator_request_id"],
            [
                "host_maintenance_receipts.installation_id",
                "host_maintenance_receipts.operator_request_id",
            ],
            ondelete="RESTRICT",
            name="fk_first_administrator_host_receipt",
        ),
        sa.CheckConstraint(
            sa.and_(sa.column("before_revision") == 0, sa.column("after_revision") == 1),
            name="ck_first_administrator_revision",
        ),
        sa.CheckConstraint(
            sa.column("organization_name") == "Inframeld", name="ck_first_administrator_org_name"
        ),
        sa.CheckConstraint(
            sa.func.octet_length(sa.column("request_fingerprint")) == 32,
            name="ck_first_administrator_fingerprint",
        ),
    )


def downgrade() -> None:
    claims = sa.table("first_administrator_bootstrap_receipts", sa.column("installation_id"))
    receipts = sa.table("host_maintenance_receipts", sa.column("mode"))
    if op.get_bind().scalar(sa.select(sa.func.count()).select_from(claims)) or op.get_bind().scalar(
        sa.select(sa.func.count())
        .select_from(receipts)
        .where(receipts.c.mode == "bootstrap-first-administrator")
    ):
        raise RuntimeError("Retained first-administrator claims prevent this downgrade.")
    op.drop_table("first_administrator_bootstrap_receipts")
    op.drop_constraint("ck_maintenance_mode", "host_maintenance_receipts", type_="check")
    op.drop_constraint("ck_maintenance_result", "host_maintenance_receipts", type_="check")
    _maintenance_constraints(bootstrap=False)
