"""Keep legacy labels while adding exact selectors and typed metadata/repair outcomes."""

import sqlalchemy as sa
from alembic import op
from migrations.types import MigrationRevisionReference

revision: str = "0014_project_metadata"
down_revision: MigrationRevisionReference = "0013_deletion_status"
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None


def _name_is_valid(column: sa.ColumnClause[str]) -> sa.ColumnElement[bool]:
    return sa.and_(
        sa.func.length(column).between(1, 63),
        sa.func.octet_length(column) == sa.func.length(column),
        column.op("~")("^[a-z]([a-z0-9-]*[a-z0-9])?$"),
    )


def upgrade() -> None:
    op.add_column("projects", sa.Column("resource_name", sa.Text(), nullable=True))
    op.add_column(
        "projects",
        sa.Column("metadata_revision", sa.BigInteger(), nullable=False, server_default="0"),
    )
    selector = sa.column("resource_name", sa.Text())
    op.create_check_constraint(
        "ck_project_resource_name", "projects", sa.or_(selector.is_(None), _name_is_valid(selector))
    )
    op.create_check_constraint(
        "ck_project_metadata_revision", "projects", sa.column("metadata_revision") >= 0
    )
    op.create_table(
        "project_name_reservations",
        sa.Column("organization_id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.Text(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("binding_revision", sa.BigInteger(), nullable=False),
        sa.Column("retired", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id"],
            ["projects.organization_id", "projects.id"],
            name="fk_project_name_project",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            _name_is_valid(sa.column("name", sa.Text())), name="ck_project_name_valid"
        ),
        sa.CheckConstraint(sa.column("binding_revision") >= 0, name="ck_project_name_revision"),
    )
    op.create_index(
        "uq_project_current_name",
        "project_name_reservations",
        ["project_id"],
        unique=True,
        postgresql_where=sa.column("retired").is_(False),
    )
    op.create_unique_constraint(
        "uq_metadata_operation_scope",
        "idempotency_reservations",
        ["operation_id", "organization_id", "project_id"],
    )
    op.create_table(
        "project_metadata_operation_results",
        sa.Column("operation_id", sa.Text(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("metadata_revision", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["operation_id", "organization_id", "project_id"],
            [
                "idempotency_reservations.operation_id",
                "idempotency_reservations.organization_id",
                "idempotency_reservations.project_id",
            ],
            name="fk_metadata_result_operation",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(sa.column("metadata_revision") >= 0, name="ck_metadata_result_revision"),
    )
    op.alter_column(
        "host_maintenance_receipts", "recovery_operation_id", existing_type=sa.Text(), nullable=True
    )
    op.alter_column(
        "host_maintenance_receipts", "released", existing_type=sa.Boolean(), nullable=True
    )
    op.drop_constraint("ck_maintenance_mode", "host_maintenance_receipts", type_="check")
    op.drop_constraint("ck_maintenance_result", "host_maintenance_receipts", type_="check")
    mode, outcome = sa.column("mode"), sa.column("outcome")
    run, deadline, at = sa.column("run_id"), sa.column("deadline"), sa.column("authorized_at")
    recovery, released = sa.column("recovery_operation_id"), sa.column("released")
    op.create_check_constraint(
        "ck_maintenance_mode",
        "host_maintenance_receipts",
        mode.in_(("resume-recovery-cleanup", "repair-stranded-authority")),
    )
    op.create_check_constraint(
        "ck_maintenance_result",
        "host_maintenance_receipts",
        sa.or_(
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
        ),
    )
    op.create_table(
        "project_metadata_repair_receipts",
        sa.Column("installation_id", sa.Uuid(), primary_key=True),
        sa.Column("operator_request_id", sa.Text(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
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
            name="fk_metadata_repair_receipt",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id"],
            ["projects.organization_id", "projects.id"],
            name="fk_metadata_repair_project",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "recipient_id"],
            ["principals.organization_id", "principals.id"],
            name="fk_metadata_repair_recipient",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            sa.and_(
                sa.column("before_revision") >= 0,
                sa.column("after_revision") == sa.column("before_revision") + 1,
            ),
            name="ck_metadata_repair_revisions",
        ),
        sa.CheckConstraint(
            sa.func.octet_length(sa.column("request_fingerprint")) == 32,
            name="ck_metadata_repair_fingerprint",
        ),
    )


def downgrade() -> None:
    receipts = sa.table("host_maintenance_receipts", sa.column("mode"))
    if op.get_bind().scalar(
        sa.select(sa.func.count())
        .select_from(receipts)
        .where(receipts.c.mode == "repair-stranded-authority")
    ):
        raise RuntimeError("Retained metadata repair receipts prevent this downgrade.")
    op.drop_table("project_metadata_repair_receipts")
    op.drop_constraint("ck_maintenance_result", "host_maintenance_receipts", type_="check")
    op.drop_constraint("ck_maintenance_mode", "host_maintenance_receipts", type_="check")
    op.create_check_constraint(
        "ck_maintenance_mode",
        "host_maintenance_receipts",
        sa.column("mode") == "resume-recovery-cleanup",
    )
    outcome, run, deadline, at, released = (
        sa.column("outcome"),
        sa.column("run_id"),
        sa.column("deadline"),
        sa.column("authorized_at"),
        sa.column("released"),
    )
    op.create_check_constraint(
        "ck_maintenance_result",
        "host_maintenance_receipts",
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
    )
    op.alter_column(
        "host_maintenance_receipts", "released", existing_type=sa.Boolean(), nullable=False
    )
    op.alter_column(
        "host_maintenance_receipts",
        "recovery_operation_id",
        existing_type=sa.Text(),
        nullable=False,
    )
    op.drop_table("project_metadata_operation_results")
    op.drop_constraint("uq_metadata_operation_scope", "idempotency_reservations", type_="unique")
    op.drop_table("project_name_reservations")
    op.drop_constraint("ck_project_metadata_revision", "projects", type_="check")
    op.drop_constraint("ck_project_resource_name", "projects", type_="check")
    op.drop_column("projects", "metadata_revision")
    op.drop_column("projects", "resource_name")
