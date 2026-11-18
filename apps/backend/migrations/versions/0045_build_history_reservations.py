"""Reserve bounded ordinary history for private Build admission."""

import sqlalchemy as sa
from alembic import op
from migrations.types import MigrationRevisionReference

revision: str = "0045_build_history_reservations"
down_revision: MigrationRevisionReference = "0044_pipeline_job_binding"
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None


def upgrade() -> None:
    op.create_table(
        "retained_history_capacity",
        sa.Column("singleton_key", sa.SmallInteger(), primary_key=True),
        sa.Column("ordinary_limit_bytes", sa.BigInteger(), nullable=False),
        sa.Column("reserved_bytes", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("singleton_key = 1", name="ck_retained_history_singleton"),
        sa.CheckConstraint(
            "ordinary_limit_bytes BETWEEN 1 AND 21474836480",
            name="ck_retained_history_ordinary_limit",
        ),
        sa.CheckConstraint("reserved_bytes >= 0", name="ck_retained_history_reserved"),
    )
    op.bulk_insert(
        sa.table(
            "retained_history_capacity",
            sa.column("singleton_key", sa.SmallInteger()),
            sa.column("ordinary_limit_bytes", sa.BigInteger()),
            sa.column("reserved_bytes", sa.BigInteger()),
        ),
        [{"singleton_key": 1, "ordinary_limit_bytes": 10 * (1 << 30), "reserved_bytes": 0}],
    )
    op.create_table(
        "retained_history_reservations",
        sa.Column("operation_id", sa.Text(), primary_key=True),
        sa.Column("installation_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("reserved_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "reserved_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("reserved_bytes > 0", name="ck_retained_history_reservation_bytes"),
        sa.ForeignKeyConstraint(
            ["installation_id"],
            ["installation_identity.installation_id"],
            name="fk_retained_history_installation",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id"],
            ["projects.organization_id", "projects.id"],
            name="fk_retained_history_project",
            ondelete="RESTRICT",
        ),
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.get_isolation_level() != "READ COMMITTED":
        raise RuntimeError("Build history downgrade requires READ COMMITTED.")

    # Take the allocator's existing exclusive turn before observing reservations.
    capacity = sa.table(
        "retained_history_capacity",
        sa.column("singleton_key", sa.SmallInteger()),
        sa.column("reserved_bytes", sa.BigInteger()),
    )
    reserved = connection.scalar(
        sa.select(capacity.c.reserved_bytes).where(capacity.c.singleton_key == 1).with_for_update()
    )
    reservations = sa.table("retained_history_reservations", sa.column("operation_id", sa.Text()))
    if reserved != 0 or connection.scalar(sa.select(reservations.c.operation_id).limit(1)):
        raise RuntimeError("Retained Build history blocks schema downgrade.")

    op.drop_table("retained_history_reservations")
    op.drop_table("retained_history_capacity")
