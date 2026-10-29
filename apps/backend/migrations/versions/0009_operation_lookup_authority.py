"""Add the nullable storage seam for original lookup authority."""

import sqlalchemy as sa
from alembic import op
from migrations.types import MigrationRevisionReference

revision: str = "0009_operation_lookup_authority"
down_revision: MigrationRevisionReference = "0008_host_maintenance_receipts"
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None


def upgrade() -> None:
    op.add_column(
        "idempotency_reservations",
        sa.Column("lookup_authority_family", sa.String(32), nullable=True),
    )
    op.add_column(
        "idempotency_reservations", sa.Column("lookup_action_id", sa.String(100), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("idempotency_reservations", "lookup_action_id")
    op.drop_column("idempotency_reservations", "lookup_authority_family")
