"""Retain safe revocation originals without coupling them to mutable key state."""

import sqlalchemy as sa
from alembic import op
from migrations.types import MigrationRevisionReference
from sqlalchemy.dialects.postgresql import ARRAY

revision: str = "0029_application_key_revocation"
down_revision: MigrationRevisionReference = "0028_application_key_issuance"
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None


def upgrade() -> None:
    adapter_type = ARRAY(sa.String(8))
    adapters = sa.column("allowed_adapters", adapter_type)
    before = sa.column("before_revision", sa.BigInteger())
    after = sa.column("access_revision", sa.BigInteger())
    created = sa.column("created_at", sa.DateTime(timezone=True))
    expires = sa.column("expires_at", sa.DateTime(timezone=True))
    revoked = sa.column("revoked_at", sa.DateTime(timezone=True))
    op.create_table(
        "application_key_revocation_results",
        sa.Column("operation_id", sa.Text(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("application_principal_id", sa.Uuid(), nullable=False),
        sa.Column("installation_id", sa.Uuid(), nullable=False),
        sa.Column("actor_principal_id", sa.Uuid(), nullable=False),
        sa.Column("key_id", sa.Uuid(), nullable=False),
        sa.Column("allowed_adapters", adapter_type, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=False),
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
            name="fk_application_key_revocation_operation",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id", "application_principal_id"],
            [
                "application_accounts.organization_id",
                "application_accounts.project_id",
                "application_accounts.principal_id",
            ],
            name="fk_application_key_revocation_account",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["installation_id"],
            ["installation_identity.installation_id"],
            name="fk_application_key_revocation_installation",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            sa.and_(
                before.between(0, 9007199254740991),
                after.between(0, 9007199254740991),
                (after - before).in_((0, 1)),
            ),
            name="ck_application_key_revocation_revision",
        ),
        sa.CheckConstraint(
            sa.and_(expires > created, revoked >= created),
            name="ck_application_key_revocation_lifecycle",
        ),
        sa.CheckConstraint(
            adapters.in_(
                tuple(
                    sa.cast(sa.literal(value, type_=adapter_type), adapter_type)
                    for value in (["http"], ["mcp"], ["http", "mcp"], ["mcp", "http"])
                )
            ),
            name="ck_application_key_revocation_adapters",
        ),
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.select(sa.func.count()).select_from(sa.table("application_key_revocation_results"))
    ):
        raise RuntimeError("Retained application-key revocation originals prevent this downgrade.")
    op.drop_table("application_key_revocation_results")
