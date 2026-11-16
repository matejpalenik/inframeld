"""Retain the first original ModelGateway issuance independently of job retention."""

import sqlalchemy as sa
from alembic import op
from migrations.types import MigrationRevisionReference

revision: str = "0040_model_dispatch_issuance"
down_revision: MigrationRevisionReference = "0039_document_upload_replay"
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None

_TABLE = "model_dispatch_issuance"
_MAX_REVISION = 2**53 - 1


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("call_id", sa.Uuid(), primary_key=True),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("fence", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("access_revision", sa.BigInteger(), nullable=False),
        sa.Column("credential_revision", sa.BigInteger(), nullable=False),
        sa.Column("adapter_revision", sa.String(128), nullable=False),
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.clock_timestamp(),
        ),
        sa.ForeignKeyConstraint(
            ["call_id"],
            ["model_call_accounting.call_id"],
            name="fk_model_dispatch_accounting_call",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            sa.and_(
                sa.column("attempt_number") > 0,
                sa.column("access_revision").between(0, _MAX_REVISION),
                sa.column("credential_revision").between(1, _MAX_REVISION),
                sa.func.length(sa.column("adapter_revision")).between(1, 128),
            ),
            name="ck_model_dispatch_original_revisions",
        ),
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.select(sa.literal(1)).select_from(sa.table(_TABLE)).limit(1)):
        raise RuntimeError("Retained model dispatch issuance prevents this downgrade.")
    op.drop_table(_TABLE)
