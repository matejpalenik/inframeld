"""Retain immutable original lookup authority without inventing legacy request meaning."""

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

    reservations = sa.table(
        "idempotency_reservations",
        sa.column("method"),
        sa.column("requested_route"),
        sa.column("project_id"),
        sa.column("lookup_authority_family"),
        sa.column("lookup_action_id"),
    )
    op.get_bind().execute(
        sa.update(reservations)
        .where(
            reservations.c.method == "POST",
            reservations.c.requested_route == "/v1/projects/{project_id}/grants",
            reservations.c.project_id.is_not(None),
        )
        .values(
            lookup_authority_family="project_grant_read", lookup_action_id="create-access-groups"
        )
    )
    op.create_check_constraint(
        "ck_idempotency_lookup_authority",
        "idempotency_reservations",
        "(lookup_authority_family IS NULL AND lookup_action_id IS NULL) OR "
        "(lookup_authority_family IS NOT NULL AND lookup_action_id IS NOT NULL AND "
        "length(trim(lookup_action_id)) > 0 AND "
        "((lookup_authority_family IN ('project_action_use', 'project_grant_read') AND project_id IS NOT NULL) OR "
        "(lookup_authority_family = 'organization_action_use' AND project_id IS NULL)))",
    )


def downgrade() -> None:
    op.drop_constraint("ck_idempotency_lookup_authority", "idempotency_reservations", type_="check")
    op.drop_column("idempotency_reservations", "lookup_action_id")
    op.drop_column("idempotency_reservations", "lookup_authority_family")
