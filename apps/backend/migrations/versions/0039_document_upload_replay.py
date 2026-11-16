"""Save the expiry of newly admitted PDF upload receipts."""

import sqlalchemy as sa
from alembic import op
from migrations.types import MigrationRevisionReference

revision: str = "0039_document_upload_replay"
down_revision: MigrationRevisionReference = "0038_document_upload"
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None


def upgrade() -> None:
    op.add_column("document_uploads", sa.Column("replay_expires_at", sa.DateTime(timezone=True)))
    op.create_check_constraint(
        "ck_document_upload_replay_state",
        "document_uploads",
        "replay_expires_at IS NULL OR state = 'admitted'",
    )


def downgrade() -> None:
    uploads = sa.table("document_uploads", sa.column("replay_expires_at"))
    if op.get_bind().scalar(
        sa.select(sa.literal(1))
        .select_from(uploads)
        .where(uploads.c.replay_expires_at.is_not(None))
        .limit(1)
    ):
        raise RuntimeError("Retained upload receipt deadlines prevent this downgrade.")

    op.drop_constraint("ck_document_upload_replay_state", "document_uploads", type_="check")
    op.drop_column("document_uploads", "replay_expires_at")
