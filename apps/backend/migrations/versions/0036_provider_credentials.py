"""Keep one encrypted credential slot and immutable safe originals per Model Connection."""

import sqlalchemy as sa
from alembic import op
from migrations.types import MigrationRevisionReference

revision: str = "0036_provider_credentials"
down_revision: MigrationRevisionReference = "0035_model_connections"
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None

_MAX_REVISION = 2**53 - 1
_SLOT = "model_connection_credentials"
_RESULTS = "model_connection_credential_results"


def upgrade() -> None:
    written_revision = sa.column("revision", sa.BigInteger())
    format_version = sa.column("format_version", sa.SmallInteger())
    algorithm = sa.column("algorithm", sa.String())
    key_id = sa.column("key_id", sa.String())
    ciphertext = sa.column("ciphertext", sa.LargeBinary())
    op.create_table(
        _SLOT,
        sa.Column("credential_id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("model_connection_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("format_version", sa.SmallInteger(), nullable=True),
        sa.Column("algorithm", sa.String(32), nullable=True),
        sa.Column("key_id", sa.String(64), nullable=True),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=True),
        sa.UniqueConstraint(
            "project_id", "model_connection_id", name="uq_model_connection_credential_slot"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id"],
            ["projects.organization_id", "projects.id"],
            name="fk_model_connection_credential_project",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "model_connection_id"],
            ["model_connections.project_id", "model_connections.id"],
            name="fk_model_connection_credential_connection",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            written_revision.between(1, _MAX_REVISION),
            name="ck_model_connection_credential_revision",
        ),
        sa.CheckConstraint(
            sa.or_(
                sa.and_(
                    format_version.is_(None),
                    algorithm.is_(None),
                    key_id.is_(None),
                    ciphertext.is_(None),
                ),
                sa.and_(
                    format_version.is_not(None),
                    format_version == 1,
                    algorithm.is_not(None),
                    algorithm == "xchacha20-poly1305",
                    key_id.is_not(None),
                    key_id.regexp_match("^[0-9a-f]{64}$"),
                    ciphertext.is_not(None),
                    sa.func.octet_length(ciphertext).between(41, 16_424),
                ),
            ),
            name="ck_model_connection_credential_cipher",
        ),
    )
    credential_id = sa.column("credential_id", sa.Uuid())
    changed_at = sa.column("credential_changed_at", sa.DateTime(timezone=True))
    present = sa.column("present", sa.Boolean())
    changed = sa.column("changed", sa.Boolean())
    op.create_table(
        _RESULTS,
        sa.Column("operation_id", sa.Text(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("model_connection_id", sa.Uuid(), nullable=False),
        sa.Column("actor_principal_id", sa.Uuid(), nullable=False),
        sa.Column("credential_id", sa.Uuid(), nullable=True),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("present", sa.Boolean(), nullable=False),
        sa.Column("changed", sa.Boolean(), nullable=False),
        sa.Column("credential_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["operation_id", "organization_id", "project_id", "actor_principal_id"],
            [
                "idempotency_reservations.operation_id",
                "idempotency_reservations.organization_id",
                "idempotency_reservations.project_id",
                "idempotency_reservations.principal_id",
            ],
            name="fk_model_connection_credential_result_operation",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "model_connection_id"],
            ["model_connections.project_id", "model_connections.id"],
            name="fk_model_connection_credential_result_connection",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            sa.or_(
                sa.and_(
                    written_revision == 0,
                    credential_id.is_(None),
                    changed_at.is_(None),
                    present.is_(False),
                    changed.is_(False),
                ),
                sa.and_(
                    written_revision.between(1, _MAX_REVISION),
                    credential_id.is_not(None),
                    changed_at.is_not(None),
                    sa.or_(changed.is_(True), present.is_(False)),
                ),
            ),
            name="ck_model_connection_credential_result_shape",
        ),
    )


def downgrade() -> None:
    connection = op.get_bind()
    if any(
        connection.scalar(sa.select(sa.exists(sa.select(1).select_from(sa.table(name)))))
        for name in (_RESULTS, _SLOT)
    ):
        raise RuntimeError("Retained model connection credentials or originals prevent downgrade.")
    op.drop_table(_RESULTS)
    op.drop_table(_SLOT)
