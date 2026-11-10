"""Store scoped future-upload audiences and immutable safe originals."""

import sqlalchemy as sa
from alembic import op
from migrations.types import MigrationRevisionReference
from sqlalchemy.dialects.postgresql import ARRAY

revision: str = "0030_project_upload_defaults"
down_revision: MigrationRevisionReference = "0029_application_key_revocation"
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None


def upgrade() -> None:
    op.create_table(
        "project_upload_default_groups",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), primary_key=True),
        sa.Column("group_id", sa.Uuid(), primary_key=True),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id"],
            ["projects.organization_id", "projects.id"],
            name="fk_upload_default_project",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "group_id"],
            ["access_groups.project_id", "access_groups.id"],
            name="fk_upload_default_group",
            ondelete="RESTRICT",
        ),
    )
    group_array = ARRAY(sa.Uuid())
    before_groups = sa.column("before_group_ids", group_array)
    groups = sa.column("group_ids", group_array)
    before = sa.column("before_revision", sa.BigInteger())
    after = sa.column("access_revision", sa.BigInteger())
    valid_after = sa.and_(
        groups.is_not(None),
        sa.func.cardinality(groups) > 0,
        sa.func.array_ndims(groups) == 1,
        sa.func.array_position(groups, sa.cast(sa.null(), sa.Uuid())).is_(None),
    )
    valid_before = sa.or_(
        before_groups.is_(None),
        sa.and_(
            before_groups.is_not(None),
            sa.func.cardinality(before_groups) > 0,
            sa.func.array_ndims(before_groups) == 1,
            sa.func.array_position(before_groups, sa.cast(sa.null(), sa.Uuid())).is_(None),
        ),
    )
    op.create_table(
        "project_upload_default_results",
        sa.Column("operation_id", sa.Text(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("actor_principal_id", sa.Uuid(), nullable=False),
        sa.Column("before_revision", sa.BigInteger(), nullable=False),
        sa.Column("access_revision", sa.BigInteger(), nullable=False),
        sa.Column("before_group_ids", group_array, nullable=True),
        sa.Column("group_ids", group_array, nullable=False),
        sa.ForeignKeyConstraint(
            ["operation_id", "organization_id", "project_id", "actor_principal_id"],
            [
                "idempotency_reservations.operation_id",
                "idempotency_reservations.organization_id",
                "idempotency_reservations.project_id",
                "idempotency_reservations.principal_id",
            ],
            name="fk_upload_default_result_operation",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            sa.and_(valid_before, valid_after), name="ck_upload_default_result_audiences"
        ),
        sa.CheckConstraint(
            sa.and_(
                before.between(0, 9007199254740991),
                after.between(0, 9007199254740991),
                after - before == sa.case((before_groups.is_distinct_from(groups), 1), else_=0),
            ),
            name="ck_upload_default_result_revisions",
        ),
    )


def downgrade() -> None:
    for name in ("project_upload_default_groups", "project_upload_default_results"):
        if op.get_bind().scalar(sa.select(sa.func.count()).select_from(sa.table(name))):
            raise RuntimeError("Retained upload defaults or originals prevent this downgrade.")
    op.drop_table("project_upload_default_results")
    op.drop_table("project_upload_default_groups")
