"""Retain artifact obligations and finite reservations outside product replay lifetime."""

import sqlalchemy as sa
from alembic import op
from migrations.types import MigrationRevisionReference

revision: str = "0015_artifact_allocation"
down_revision: MigrationRevisionReference = "0014_project_metadata"
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None


def upgrade() -> None:
    op.create_table(
        "artifact_storage_capacity",
        sa.Column("installation_id", sa.Uuid(), primary_key=True),
        sa.Column("spool_reserved_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("protected_reserved_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("occupied_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.CheckConstraint(
            "spool_reserved_bytes BETWEEN 0 AND 2147483648", name="ck_artifact_spool_capacity"
        ),
        sa.CheckConstraint(
            "protected_reserved_bytes BETWEEN 0 AND 107374182400",
            name="ck_artifact_protected_capacity",
        ),
        sa.CheckConstraint(
            "occupied_bytes BETWEEN 0 AND protected_reserved_bytes",
            name="ck_artifact_occupied_capacity",
        ),
    )
    op.create_table(
        "artifact_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("artifact_id", sa.Uuid(), nullable=False),
        sa.Column("installation_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False, server_default="allocated"),
        sa.Column("length", sa.BigInteger(), nullable=True),
        sa.Column("digest", sa.LargeBinary(), nullable=True),
        sa.Column("published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("retired", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("put_pending", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("put_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("remote_removed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("retention_protected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.clock_timestamp(),
        ),
        sa.UniqueConstraint(
            "id",
            "installation_id",
            "organization_id",
            "project_id",
            name="uq_artifact_attempt_scope",
        ),
        sa.CheckConstraint(
            "(length IS NULL AND digest IS NULL) OR (length IS NOT NULL AND length BETWEEN 0 AND 268435456 AND digest IS NOT NULL AND octet_length(digest) = 32)",
            name="ck_artifact_sealed_content",
        ),
        sa.CheckConstraint(
            "NOT published OR (length IS NOT NULL AND put_confirmed AND NOT retired)",
            name="ck_artifact_publication",
        ),
    )
    op.create_index(
        "uq_artifact_published_identity",
        "artifact_attempts",
        ["artifact_id"],
        unique=True,
        postgresql_where=sa.column("published").is_(True),
    )
    op.create_table(
        "artifact_staging_reservations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "attempt_id",
            sa.Uuid(),
            sa.ForeignKey("artifact_attempts.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("limit_bytes", sa.BigInteger(), nullable=False),
        sa.Column("local_reserved_bytes", sa.BigInteger(), nullable=False),
        sa.Column("remote_reserved_bytes", sa.BigInteger(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("staging_removed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.CheckConstraint(
            "limit_bytes BETWEEN 1 AND 268435456", name="ck_artifact_reservation_limit"
        ),
        sa.CheckConstraint(
            "local_reserved_bytes BETWEEN 0 AND limit_bytes AND remote_reserved_bytes BETWEEN 0 AND limit_bytes",
            name="ck_artifact_reserved_bytes",
        ),
        sa.CheckConstraint(
            "NOT released OR local_reserved_bytes = 0", name="ck_artifact_released_local_bytes"
        ),
    )
    op.create_table(
        "artifact_cleanup_obligations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("installation_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column(
            "staging_reservation_id",
            sa.Uuid(),
            sa.ForeignKey("artifact_staging_reservations.id", ondelete="RESTRICT"),
            nullable=True,
            unique=True,
        ),
        sa.Column("origin_kind", sa.String(32), nullable=False),
        sa.Column("origin_operation_id", sa.Text(), nullable=True),
        sa.Column("origin_attempt_id", sa.Uuid(), nullable=True),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("transfer_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retirement_authorized", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("physically_complete", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("execution_status", sa.String(32), nullable=True),
        sa.Column("execution_reason", sa.String(100), nullable=True),
        sa.CheckConstraint(
            "kind IN ('abandoned_staging', 'erasure', 'retention_expiry')",
            name="ck_artifact_cleanup_kind",
        ),
        sa.CheckConstraint(
            "(kind = 'abandoned_staging' AND staging_reservation_id IS NOT NULL) OR (kind IN ('erasure', 'retention_expiry') AND staging_reservation_id IS NULL)",
            name="ck_artifact_original_staging_binding",
        ),
        sa.CheckConstraint(
            "(origin_kind = 'business' AND origin_operation_id IS NOT NULL AND origin_attempt_id IS NULL) OR (origin_kind = 'unadmitted_staging' AND origin_operation_id IS NULL AND origin_attempt_id IS NOT NULL)",
            name="ck_artifact_cleanup_origin",
        ),
        sa.UniqueConstraint(
            "id",
            "installation_id",
            "organization_id",
            "project_id",
            name="uq_artifact_obligation_scope",
        ),
    )
    op.create_table(
        "artifact_cleanup_targets",
        sa.Column(
            "obligation_id",
            sa.Uuid(),
            sa.ForeignKey("artifact_cleanup_obligations.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column(
            "attempt_id",
            sa.Uuid(),
            sa.ForeignKey("artifact_attempts.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column(
            "staging_confirmed_removed", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "remote_confirmed_removed", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    for name, type_ in [
        ("operation_id", sa.Text()),
        ("principal_id", sa.Uuid()),
        ("principal_kind", sa.String(32)),
        ("action_id", sa.String(100)),
    ]:
        op.alter_column("durable_jobs", name, existing_type=type_, nullable=True)
    op.add_column(
        "durable_jobs",
        sa.Column("binding_kind", sa.String(32), nullable=False, server_default="product"),
    )
    op.add_column("durable_jobs", sa.Column("cleanup_obligation_id", sa.Uuid(), nullable=True))
    op.create_unique_constraint(
        "uq_job_cleanup_obligation", "durable_jobs", ["cleanup_obligation_id"]
    )
    op.create_foreign_key(
        "fk_job_cleanup_scope",
        "durable_jobs",
        "artifact_cleanup_obligations",
        ["cleanup_obligation_id", "installation_id", "organization_id", "project_id"],
        ["id", "installation_id", "organization_id", "project_id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_job_closed_binding",
        "durable_jobs",
        "(binding_kind = 'product' AND operation_id IS NOT NULL AND principal_id IS NOT NULL AND principal_kind IS NOT NULL AND action_id IS NOT NULL AND cleanup_obligation_id IS NULL) OR (binding_kind = 'artifact_cleanup' AND cleanup_obligation_id IS NOT NULL AND operation_id IS NULL AND principal_id IS NULL AND principal_kind IS NULL AND action_id IS NULL AND human_authority IS NULL AND human_subject IS NULL AND human_version IS NULL)",
    )


def downgrade() -> None:
    attempts = sa.table("artifact_attempts", sa.column("id"))
    obligations = sa.table("artifact_cleanup_obligations", sa.column("id"))
    if op.get_bind().scalar(
        sa.select(sa.func.count()).select_from(attempts)
    ) or op.get_bind().scalar(sa.select(sa.func.count()).select_from(obligations)):
        raise RuntimeError("Retained artifact ownership prevents this downgrade.")
    op.drop_constraint("ck_job_closed_binding", "durable_jobs", type_="check")
    op.drop_constraint("fk_job_cleanup_scope", "durable_jobs", type_="foreignkey")
    op.drop_constraint("uq_job_cleanup_obligation", "durable_jobs", type_="unique")
    op.drop_column("durable_jobs", "cleanup_obligation_id")
    op.drop_column("durable_jobs", "binding_kind")
    for name, type_ in [
        ("operation_id", sa.Text()),
        ("principal_id", sa.Uuid()),
        ("principal_kind", sa.String(32)),
        ("action_id", sa.String(100)),
    ]:
        op.alter_column("durable_jobs", name, existing_type=type_, nullable=False)
    op.drop_table("artifact_cleanup_targets")
    op.drop_table("artifact_cleanup_obligations")
    op.drop_table("artifact_staging_reservations")
    op.drop_index("uq_artifact_published_identity", table_name="artifact_attempts")
    op.drop_table("artifact_attempts")
    op.drop_table("artifact_storage_capacity")
