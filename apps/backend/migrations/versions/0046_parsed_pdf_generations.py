"""Keep verified canonical PDF artifacts and ordered chunk ranges."""

import sqlalchemy as sa
from alembic import op
from migrations.types import MigrationRevisionReference

revision: str = "0046_parsed_pdf_generations"
down_revision: MigrationRevisionReference = "0045_build_history_reservations"
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None

_SCOPE = ["installation_id", "organization_id", "project_id"]


def upgrade() -> None:
    op.create_table(
        "parsed_pdf_generations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("installation_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("processing_profile_id", sa.Uuid(), nullable=False),
        sa.Column("canonical_artifact_attempt_id", sa.Uuid(), nullable=False),
        sa.Column("canonical_identity", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "octet_length(canonical_identity) = 32", name="ck_pdf_canonical_identity"
        ),
        sa.ForeignKeyConstraint(
            [*_SCOPE, "document_id", "document_version_id"],
            [
                *(f"document_versions.{part}" for part in _SCOPE),
                "document_versions.document_id",
                "document_versions.id",
            ],
            name="fk_pdf_generation_source",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id", "processing_profile_id"],
            [
                "processing_profiles.organization_id",
                "processing_profiles.project_id",
                "processing_profiles.id",
            ],
            name="fk_pdf_generation_profile",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["canonical_artifact_attempt_id", *_SCOPE],
            ["artifact_attempts.id", *(f"artifact_attempts.{part}" for part in _SCOPE)],
            name="fk_pdf_generation_canonical_artifact",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("canonical_artifact_attempt_id", name="uq_pdf_generation_attempt"),
    )
    op.create_table(
        "parsed_pdf_chunks",
        sa.Column("generation_id", sa.Uuid(), primary_key=True),
        sa.Column("ordinal", sa.Integer(), primary_key=True),
        sa.Column("start_codepoint", sa.Integer(), nullable=False),
        sa.Column("end_codepoint", sa.Integer(), nullable=False),
        sa.CheckConstraint("ordinal >= 0 AND ordinal < 2000", name="ck_pdf_chunk_ordinal"),
        sa.CheckConstraint(
            "start_codepoint >= 0 AND start_codepoint < end_codepoint AND end_codepoint <= 10485760",
            name="ck_pdf_chunk_half_open",
        ),
        sa.ForeignKeyConstraint(
            ["generation_id"],
            ["parsed_pdf_generations.id"],
            name="fk_pdf_chunk_generation",
            ondelete="RESTRICT",
        ),
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.get_isolation_level() != "READ COMMITTED":
        raise RuntimeError("Parsed PDF output downgrade requires READ COMMITTED.")

    # Lock the reference table before checking for retained output.
    op.drop_constraint("fk_pdf_chunk_generation", "parsed_pdf_chunks", type_="foreignkey")
    op.drop_constraint("ck_pdf_canonical_identity", "parsed_pdf_generations", type_="check")
    generations = sa.table("parsed_pdf_generations", sa.column("id", sa.Uuid()))
    if connection.scalar(sa.select(generations.c.id).limit(1)) is not None:
        raise RuntimeError("Retained PDF generations block schema downgrade.")

    op.drop_table("parsed_pdf_chunks")
    op.drop_table("parsed_pdf_generations")
