"""Keep exact original Project grant outcomes after current assignments change."""

import sqlalchemy as sa
from alembic import op
from migrations.types import MigrationRevisionReference

revision: str = "0022_project_grant_results"
down_revision: MigrationRevisionReference = "0021_job_effect_observations"
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None


def upgrade() -> None:
    before = sa.column("before_revision", sa.BigInteger())
    after = sa.column("access_revision", sa.BigInteger())
    previous = sa.column("before_can_grant", sa.Boolean())
    level = sa.column("can_grant", sa.Boolean())
    changed = sa.column("changed", sa.Boolean())
    kind = sa.column("change_kind", sa.String())
    status = sa.column("status_code", sa.Integer())
    op.create_table(
        "project_action_grant_operation_results",
        sa.Column("operation_id", sa.Text(), primary_key=True),
        sa.Column("installation_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("actor_principal_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_principal_id", sa.Uuid(), nullable=False),
        sa.Column("action_id", sa.String(100), nullable=False),
        sa.Column("change_kind", sa.String(16), nullable=False),
        sa.Column("before_revision", sa.BigInteger(), nullable=False),
        sa.Column("access_revision", sa.BigInteger(), nullable=False),
        sa.Column("changed", sa.Boolean(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("before_can_grant", sa.Boolean(), nullable=True),
        sa.Column("can_grant", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(
            ["installation_id"],
            ["installation_identity.installation_id"],
            name="fk_project_grant_result_installation",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["operation_id", "organization_id", "actor_principal_id"],
            [
                "idempotency_reservations.operation_id",
                "idempotency_reservations.organization_id",
                "idempotency_reservations.principal_id",
            ],
            name="fk_project_grant_result_operation",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id"],
            ["projects.organization_id", "projects.id"],
            name="fk_project_grant_result_project",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "recipient_principal_id"],
            ["principals.organization_id", "principals.id"],
            name="fk_project_grant_result_recipient",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            sa.func.length(sa.func.trim(sa.column("action_id", sa.String()))) > 0,
            name="ck_project_grant_result_action",
        ),
        sa.CheckConstraint(kind.in_(("set", "remove")), name="ck_project_grant_result_kind"),
        sa.CheckConstraint(
            sa.and_(before >= 0, after >= 0), name="ck_project_grant_result_revisions"
        ),
        sa.CheckConstraint(
            sa.or_(
                sa.and_(kind == "set", level.is_not(None)),
                sa.and_(kind == "remove", level.is_(None)),
            ),
            name="ck_project_grant_result_level",
        ),
        sa.CheckConstraint(
            changed == previous.is_distinct_from(level), name="ck_project_grant_result_changed"
        ),
        sa.CheckConstraint(
            sa.or_(
                sa.and_(changed.is_(True), after > before, after - before == 1),
                sa.and_(changed.is_(False), after == before),
            ),
            name="ck_project_grant_result_revision_change",
        ),
        sa.CheckConstraint(
            sa.or_(
                sa.and_(kind == "set", previous.is_(None), status == 201),
                sa.and_(sa.or_(kind == "remove", previous.is_not(None)), status == 200),
            ),
            name="ck_project_grant_result_original_status",
        ),
    )


def downgrade() -> None:
    results = sa.table("project_action_grant_operation_results", sa.column("operation_id"))
    if op.get_bind().scalar(sa.select(sa.func.count()).select_from(results)):
        raise RuntimeError("Retained grant outcomes prevent this downgrade.")
    op.drop_table("project_action_grant_operation_results")
