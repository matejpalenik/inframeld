"""Initialize one persistent installation identity."""

from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from migrations.types import MigrationRevisionReference

revision: str = "0003_installation_identity"
down_revision: MigrationRevisionReference = "0002_idempotency_reservations"
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None


def upgrade() -> None:
    identity_table = op.create_table(
        "installation_identity",
        sa.Column("singleton_key", sa.SmallInteger(), autoincrement=False, nullable=False),
        sa.Column("installation_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("singleton_key", name="pk_installation_identity"),
        sa.CheckConstraint(
            sa.column("singleton_key", sa.SmallInteger()) == 1,
            name="ck_installation_identity_singleton",
        ),
        sa.UniqueConstraint("installation_id", name="uq_installation_identity_id"),
    )
    op.bulk_insert(
        identity_table,
        [{"singleton_key": 1, "installation_id": uuid4()}],
    )


def downgrade() -> None:
    """Preserve installation identity instead of allowing a silent reset."""
    raise RuntimeError("Downgrading installation identity is unsupported.")
