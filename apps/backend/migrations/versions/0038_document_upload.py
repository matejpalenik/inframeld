"""Store pending PDF admissions and their immutable Document versions."""

import sqlalchemy as sa
from alembic import op
from migrations.types import MigrationRevisionReference
from sqlalchemy.dialects.postgresql import ARRAY

revision: str = "0038_document_upload"
down_revision: MigrationRevisionReference = "0037_processing_profiles"
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None


def upgrade() -> None:
    op.create_table(
        "document_uploads",
        sa.Column("operation_id", sa.Text(), primary_key=True),
        sa.Column("installation_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("actor_principal_id", sa.Uuid(), nullable=False),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("version_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("artifact_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("attempt_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("reservation_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("obligation_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("cleanup_job_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("group_ids", ARRAY(sa.Uuid()), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id"],
            ["projects.organization_id", "projects.id"],
            name="fk_document_upload_project",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "actor_principal_id"],
            ["principals.organization_id", "principals.id"],
            name="fk_document_upload_actor",
            ondelete="RESTRICT",
        ),
        _attempt_reference("attempt_id", "fk_document_upload_attempt"),
        sa.ForeignKeyConstraint(
            ["reservation_id"],
            ["artifact_staging_reservations.id"],
            name="fk_document_upload_reservation",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["obligation_id"],
            ["artifact_cleanup_obligations.id"],
            name="fk_document_upload_obligation",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["cleanup_job_id"],
            ["durable_jobs.id"],
            name="fk_document_upload_cleanup_job",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "installation_id",
            "organization_id",
            "project_id",
            "actor_principal_id",
            "request_key",
            name="uq_document_upload_original_key",
        ),
        sa.UniqueConstraint("project_id", "operation_id", name="uq_document_upload_project_id"),
        sa.CheckConstraint(
            "state IN ('pending', 'admitted', 'unused')", name="ck_document_upload_state"
        ),
        sa.CheckConstraint(
            "cardinality(group_ids) > 0 AND array_ndims(group_ids) = 1 "
            "AND array_position(group_ids, NULL::uuid) IS NULL",
            name="ck_document_upload_audience",
        ),
    )
    op.create_index(
        "ix_document_upload_pending_installation",
        "document_uploads",
        ["installation_id"],
        postgresql_where=sa.column("state") == "pending",
    )
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("installation_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id"],
            ["projects.organization_id", "projects.id"],
            name="fk_document_project",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("project_id", "id", name="uq_document_project_id"),
        sa.UniqueConstraint(
            "installation_id", "organization_id", "project_id", "id", name="uq_document_scope_id"
        ),
    )
    op.create_table(
        "document_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("installation_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("media_type", sa.Text(), nullable=False),
        sa.Column("length", sa.BigInteger(), nullable=False),
        sa.Column("digest", sa.LargeBinary(), nullable=False),
        sa.ForeignKeyConstraint(
            ["installation_id", "organization_id", "project_id", "document_id"],
            [
                "documents.installation_id",
                "documents.organization_id",
                "documents.project_id",
                "documents.id",
            ],
            name="fk_document_version_document",
            ondelete="RESTRICT",
        ),
        _attempt_reference("attempt_id", "fk_document_version_attempt"),
        sa.UniqueConstraint("document_id", "digest", name="uq_document_version_content"),
        sa.CheckConstraint(
            "length BETWEEN 1 AND 26214400 AND octet_length(digest) = 32",
            name="ck_document_version_bytes",
        ),
    )
    op.create_table(
        "document_upload_groups",
        sa.Column("operation_id", sa.Text(), primary_key=True),
        sa.Column("group_id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id", "operation_id"],
            ["document_uploads.project_id", "document_uploads.operation_id"],
            name="fk_document_upload_group_original",
            ondelete="RESTRICT",
        ),
        _group_reference("fk_document_upload_group"),
    )
    op.create_table(
        "document_groups",
        sa.Column("document_id", sa.Uuid(), primary_key=True),
        sa.Column("group_id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id", "document_id"],
            ["documents.project_id", "documents.id"],
            name="fk_document_group_document",
            ondelete="RESTRICT",
        ),
        _group_reference("fk_document_group"),
    )


def downgrade() -> None:
    names = (
        "document_groups",
        "document_upload_groups",
        "document_versions",
        "documents",
        "document_uploads",
    )
    for name in names:
        if op.get_bind().scalar(sa.select(sa.literal(1)).select_from(sa.table(name)).limit(1)):
            raise RuntimeError("Retained Document uploads or versions prevent this downgrade.")
    for name in names:
        op.drop_table(name)


def _attempt_reference(column: str, name: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column, "installation_id", "organization_id", "project_id"],
        [
            "artifact_attempts.id",
            "artifact_attempts.installation_id",
            "artifact_attempts.organization_id",
            "artifact_attempts.project_id",
        ],
        name=name,
        ondelete="RESTRICT",
    )


def _group_reference(name: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["project_id", "group_id"],
        ["access_groups.project_id", "access_groups.id"],
        name=name,
        ondelete="RESTRICT",
    )
