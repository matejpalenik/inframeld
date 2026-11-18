"""Record the retained Document-wide erasure fence."""

import sqlalchemy as sa
from alembic import op
from migrations.types import MigrationRevisionReference

revision: str = "0042_document_erasure_fence"
down_revision: MigrationRevisionReference = "0041_embedding_profiles"
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None

_TABLE = "documents"
_PAIR = "ck_document_erasure_pair"


def upgrade() -> None:
    op.add_column(_TABLE, sa.Column("erasure_operation_id", sa.Text()))
    op.add_column(_TABLE, sa.Column("erasure_blocked_at", sa.DateTime(timezone=True)))

    operation = sa.column("erasure_operation_id", sa.Text())
    blocked = sa.column("erasure_blocked_at", sa.DateTime(timezone=True))
    op.create_check_constraint(
        _PAIR,
        _TABLE,
        sa.or_(
            sa.and_(operation.is_(None), blocked.is_(None)),
            sa.and_(
                operation.is_not(None),
                blocked.is_not(None),
                sa.func.btrim(operation) != "",
            ),
        ),
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.get_isolation_level() != "READ COMMITTED":
        raise RuntimeError("Document erasure downgrade requires READ COMMITTED.")

    # This transactional ALTER holds the table lock before checking for a retained block.
    op.drop_constraint(_PAIR, _TABLE, type_="check")
    operation = sa.column("erasure_operation_id", sa.Text())
    blocked = sa.column("erasure_blocked_at", sa.DateTime(timezone=True))
    documents = sa.table(_TABLE, operation, blocked)
    marked = (
        sa.select(sa.literal(1))
        .select_from(documents)
        .where(sa.or_(operation.is_not(None), blocked.is_not(None)))
        .limit(1)
    )
    if connection.scalar(marked) is not None:
        raise RuntimeError("Retained Document erasure blocks schema downgrade.")

    op.drop_column(_TABLE, "erasure_blocked_at")
    op.drop_column(_TABLE, "erasure_operation_id")
