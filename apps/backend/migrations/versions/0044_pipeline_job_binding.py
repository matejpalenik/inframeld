"""Bind an admitted Build job to its exact Pipeline."""

import sqlalchemy as sa
from alembic import op
from migrations.types import MigrationRevisionReference

revision: str = "0044_pipeline_job_binding"
down_revision: MigrationRevisionReference = "0043_build_resources"
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None


def upgrade() -> None:
    op.add_column("durable_jobs", sa.Column("pipeline_id", sa.Uuid()))
    kind = sa.column("binding_kind", sa.String())
    action = sa.column("action_id", sa.String())
    pipeline = sa.column("pipeline_id", sa.Uuid())
    op.create_check_constraint(
        "ck_durable_jobs_pipeline_binding",
        "durable_jobs",
        sa.and_(kind == "product", action.is_not_distinct_from("build-pipeline"))
        == pipeline.is_not(None),
    )
    op.create_foreign_key(
        "fk_durable_job_exact_pipeline",
        "durable_jobs",
        "pipelines",
        ["installation_id", "organization_id", "project_id", "pipeline_id"],
        ["installation_id", "organization_id", "project_id", "id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.get_isolation_level() != "READ COMMITTED":
        raise RuntimeError("Pipeline job binding downgrade requires READ COMMITTED.")

    # Keep the table locked while checking for original jobs that need their Pipeline.
    op.drop_constraint("ck_durable_jobs_pipeline_binding", "durable_jobs", type_="check")
    pipeline = sa.column("pipeline_id", sa.Uuid())
    jobs = sa.table("durable_jobs", pipeline)
    if (
        connection.scalar(
            sa.select(pipeline).select_from(jobs).where(pipeline.is_not(None)).limit(1)
        )
        is not None
    ):
        raise RuntimeError("Retained Pipeline jobs block schema downgrade.")

    op.drop_constraint("fk_durable_job_exact_pipeline", "durable_jobs", type_="foreignkey")
    op.drop_column("durable_jobs", "pipeline_id")
