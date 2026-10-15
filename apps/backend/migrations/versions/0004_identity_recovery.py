"""Persist original recovery operations and their temporary product-access blocks."""

import sqlalchemy as sa
from alembic import op
from migrations.types import MigrationRevisionReference

revision: str = "0004_identity_recovery"
down_revision: MigrationRevisionReference = "0003_installation_identity"
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None


def upgrade() -> None:
    kratos_state = sa.column("kratos_cleanup_state", sa.String(16))
    hydra_state = sa.column("hydra_cleanup_state", sa.String(16))
    released_at = sa.column("released_at", sa.DateTime(timezone=True))
    cleanup_states = ("pending", "confirmed", "failed", "uncertain")

    op.create_table(
        "identity_recovery_admissions",
        sa.Column("operation_id", sa.Text(), nullable=False),
        sa.Column("installation_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("authority", sa.Text(), nullable=False),
        sa.Column("flow_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("event_kind", sa.String(20), nullable=False),
        sa.Column("kratos_cleanup_state", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("hydra_cleanup_state", sa.String(16), nullable=False, server_default="pending"),
        sa.Column(
            "admitted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("operation_id", name="pk_identity_recovery_admissions"),
        sa.ForeignKeyConstraint(
            ["installation_id"],
            ["installation_identity.installation_id"],
            name="fk_identity_recovery_admissions_installation",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "installation_id",
            "authority",
            "flow_id",
            name="uq_identity_recovery_admissions_flow",
        ),
        sa.CheckConstraint(
            sa.column("event_kind", sa.String(20)).in_(("recovery", "password-reset")),
            name="ck_identity_recovery_admissions_event_kind",
        ),
        sa.CheckConstraint(
            sa.and_(kratos_state.in_(cleanup_states), hydra_state.in_(cleanup_states)),
            name="ck_identity_recovery_admissions_cleanup_states",
        ),
        sa.CheckConstraint(
            sa.or_(
                released_at.is_(None),
                sa.and_(kratos_state == "confirmed", hydra_state == "confirmed"),
            ),
            name="ck_identity_recovery_admissions_release",
        ),
        sa.CheckConstraint(
            sa.and_(
                sa.func.length(sa.func.btrim(sa.column("operation_id", sa.Text()))) > 0,
                sa.func.length(sa.func.btrim(sa.column("authority", sa.Text()))) > 0,
                sa.func.length(sa.func.btrim(sa.column("subject", sa.Text()))) > 0,
            ),
            name="ck_identity_recovery_admissions_nonblank",
        ),
    )
    op.create_index(
        "ix_identity_recovery_admissions_pending",
        "identity_recovery_admissions",
        ["installation_id", "authority", "subject"],
        postgresql_where=released_at.is_(None),
    )


def downgrade() -> None:
    """Preserve pending blocks and completed replay history during schema changes."""
    raise RuntimeError("Downgrading recovery admissions is unsupported.")
