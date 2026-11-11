"""Retain the exact completed application retirement with its native reservation."""

import sqlalchemy as sa
from alembic import op
from migrations.types import MigrationRevisionReference

revision: str = "0032_application_retirement"
down_revision: MigrationRevisionReference = "0031_project_deletion"
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None

_TABLE = "application_account_deletion_results"
_MAX_REVISION = 9007199254740991


def upgrade() -> None:
    before = sa.column("before_revision", sa.BigInteger())
    after = sa.column("access_revision", sa.BigInteger())
    op.create_table(
        _TABLE,
        sa.Column("operation_id", sa.Text(), primary_key=True),
        sa.Column("installation_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("actor_principal_id", sa.Uuid(), nullable=False),
        sa.Column("application_principal_id", sa.Uuid(), nullable=False),
        sa.Column("before_revision", sa.BigInteger(), nullable=False),
        sa.Column("access_revision", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["operation_id", "organization_id", "project_id", "actor_principal_id"],
            [
                "idempotency_reservations.operation_id",
                "idempotency_reservations.organization_id",
                "idempotency_reservations.project_id",
                "idempotency_reservations.principal_id",
            ],
            name="fk_application_retirement_operation",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id", "application_principal_id"],
            [
                "application_accounts.organization_id",
                "application_accounts.project_id",
                "application_accounts.principal_id",
            ],
            name="fk_application_retirement_account",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["installation_id"],
            ["installation_identity.installation_id"],
            name="fk_application_retirement_installation",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            sa.and_(
                before.between(0, _MAX_REVISION - 1),
                after.between(1, _MAX_REVISION),
                after - before == 1,
            ),
            name="ck_application_retirement_revision",
        ),
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.select(sa.func.count()).select_from(sa.table(_TABLE))):
        raise RuntimeError("Retained application retirement originals prevent this downgrade.")
    op.drop_table(_TABLE)
