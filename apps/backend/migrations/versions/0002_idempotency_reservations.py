"""Create durable scoped operation reservations."""

import sqlalchemy as sa
from alembic import op
from migrations.types import MigrationRevisionReference

revision: str = "0002_idempotency_reservations"
down_revision: MigrationRevisionReference = "0001_initial"
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None


def upgrade() -> None:
    """Create the reservation record and enforce one operation per scoped key."""
    op.create_table(
        "idempotency_reservations",
        sa.Column("operation_id", sa.Text(), primary_key=True),
        sa.Column("principal_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("requested_route", sa.Text(), nullable=False),
        sa.Column("request_key", sa.String(length=128), nullable=False),
        sa.Column("request_fingerprint", sa.LargeBinary(), nullable=False),
        sa.Column(
            "state",
            sa.String(length=32),
            nullable=False,
            server_default="in_progress",
        ),
        sa.Column("replay_kind", sa.String(length=32), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "principal_id"],
            ["principals.organization_id", "principals.id"],
            name="fk_idempotency_reservations_principal",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id"],
            ["projects.organization_id", "projects.id"],
            name="fk_idempotency_reservations_project",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "principal_id",
            "organization_id",
            "project_id",
            "method",
            "requested_route",
            "request_key",
            name="uq_idempotency_reservations_scope",
            postgresql_nulls_not_distinct=True,
        ),
        sa.CheckConstraint(
            "method IN ('POST', 'PUT', 'PATCH', 'DELETE')",
            name="ck_idempotency_reservations_method",
        ),
        sa.CheckConstraint(
            "length(trim(requested_route)) > 0 AND length(trim(request_key)) > 0",
            name="ck_idempotency_reservations_nonblank",
        ),
        sa.CheckConstraint(
            "state IN ('in_progress', 'replayable', 'recovery_required')",
            name="ck_idempotency_reservations_state",
        ),
        sa.CheckConstraint(
            "(state = 'replayable' AND replay_kind IS NOT NULL "
            "AND replay_kind IN ('async_job', 'safe_result', 'issued_secret', 'answer_receipt')) "
            "OR (state IN ('in_progress', 'recovery_required') AND replay_kind IS NULL)",
            name="ck_idempotency_reservations_replay_kind",
        ),
    )


def downgrade() -> None:
    """Remove the reservation record."""
    op.drop_table("idempotency_reservations")
