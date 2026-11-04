"""Retain original membership outcomes independently of removable relationships."""

import sqlalchemy as sa
from alembic import op
from migrations.types import MigrationRevisionReference

revision: str = "0020_project_membership"
down_revision: MigrationRevisionReference = "0019_human_admission"
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None


def upgrade() -> None:
    before = sa.column("before_revision", sa.BigInteger())
    after = sa.column("access_revision", sa.BigInteger())
    changed = sa.column("changed", sa.Boolean())
    kind = sa.column("change_kind", sa.String())
    status = sa.column("status_code", sa.Integer())
    op.create_table(
        "project_membership_operation_results",
        sa.Column("operation_id", sa.Text(), primary_key=True),
        sa.Column("installation_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("actor_principal_id", sa.Uuid(), nullable=False),
        sa.Column("principal_id", sa.Uuid(), nullable=False),
        sa.Column("change_kind", sa.String(length=16), nullable=False),
        sa.Column("before_revision", sa.BigInteger(), nullable=False),
        sa.Column("access_revision", sa.BigInteger(), nullable=False),
        sa.Column("changed", sa.Boolean(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["installation_id"],
            ["installation_identity.installation_id"],
            name="fk_project_membership_result_installation",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["operation_id", "organization_id", "actor_principal_id"],
            [
                "idempotency_reservations.operation_id",
                "idempotency_reservations.organization_id",
                "idempotency_reservations.principal_id",
            ],
            name="fk_project_membership_result_operation",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id"],
            ["projects.organization_id", "projects.id"],
            name="fk_project_membership_result_project",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "principal_id"],
            ["principals.organization_id", "principals.id"],
            name="fk_project_membership_result_recipient",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(kind.in_(("add", "remove")), name="ck_project_membership_result_kind"),
        sa.CheckConstraint(
            sa.and_(before >= 0, after >= 0), name="ck_project_membership_result_revisions"
        ),
        sa.CheckConstraint(
            sa.or_(
                sa.and_(
                    changed.is_(True),
                    after == before + 1,
                    sa.or_(
                        sa.and_(kind == "add", status == 201),
                        sa.and_(kind == "remove", status == 200),
                    ),
                ),
                sa.and_(changed.is_(False), after == before, status == 200),
            ),
            name="ck_project_membership_original_outcome",
        ),
    )


def downgrade() -> None:
    results = sa.table("project_membership_operation_results", sa.column("operation_id"))
    if op.get_bind().scalar(sa.select(sa.func.count()).select_from(results)):
        raise RuntimeError("Retained membership outcomes prevent this downgrade.")
    op.drop_table("project_membership_operation_results")
