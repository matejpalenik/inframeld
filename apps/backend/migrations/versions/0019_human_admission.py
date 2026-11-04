"""Retain scoped original human admission without coupling it to starter resources."""

import sqlalchemy as sa
from alembic import op
from migrations.types import MigrationRevisionReference

revision: str = "0019_human_admission"
down_revision: MigrationRevisionReference = "0018_spending_accounting"
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_human_admission_identity_scope",
        "human_identity_links",
        ["authority", "subject", "organization_id", "principal_id"],
    )
    changed = sa.column("changed", sa.Boolean())
    status = sa.column("status_code", sa.Integer())
    before = sa.column("before_revision", sa.BigInteger())
    after = sa.column("access_revision", sa.BigInteger())
    op.create_table(
        "human_admission_operation_results",
        sa.Column("operation_id", sa.Text(), primary_key=True),
        sa.Column("installation_id", sa.Uuid(), nullable=False),
        sa.Column("authority", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("actor_principal_id", sa.Uuid(), nullable=False),
        sa.Column("principal_id", sa.Uuid(), nullable=False),
        sa.Column("before_revision", sa.BigInteger(), nullable=False),
        sa.Column("access_revision", sa.BigInteger(), nullable=False),
        sa.Column("changed", sa.Boolean(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["installation_id"],
            ["installation_identity.installation_id"],
            name="fk_human_admission_installation",
            ondelete="RESTRICT",
        ),
        # Reuse the existing parent scope key created by 0017.
        sa.ForeignKeyConstraint(
            ["operation_id", "organization_id", "actor_principal_id"],
            [
                "idempotency_reservations.operation_id",
                "idempotency_reservations.organization_id",
                "idempotency_reservations.principal_id",
            ],
            name="fk_human_admission_operation",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["authority", "subject", "organization_id", "principal_id"],
            [
                "human_identity_links.authority",
                "human_identity_links.subject",
                "human_identity_links.organization_id",
                "human_identity_links.principal_id",
            ],
            name="fk_human_admission_identity",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(sa.and_(before >= 0, after >= 0), name="ck_human_admission_revisions"),
        sa.CheckConstraint(
            sa.or_(
                sa.and_(changed.is_(True), status == 201, after == before + 1),
                sa.and_(changed.is_(False), status == 200, after == before),
            ),
            name="ck_human_admission_original_outcome",
        ),
    )


def downgrade() -> None:
    results = sa.table("human_admission_operation_results", sa.column("operation_id"))
    if op.get_bind().scalar(sa.select(sa.func.count()).select_from(results)):
        raise RuntimeError("Retained human admission outcomes prevent this downgrade.")
    # Dropping result storage never deletes the principal, link or generation.
    op.drop_table("human_admission_operation_results")
    op.drop_constraint("uq_human_admission_identity_scope", "human_identity_links", type_="unique")
