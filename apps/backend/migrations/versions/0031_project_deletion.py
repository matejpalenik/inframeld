"""Retain original Project deletion independently of local child execution."""

import sqlalchemy as sa
from alembic import op
from migrations.types import MigrationRevisionReference

revision: str = "0031_project_deletion"
down_revision: MigrationRevisionReference = "0030_project_upload_defaults"
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None


def _binding_shape(*, deletion: bool) -> sa.ColumnElement[bool]:
    kind = sa.column("binding_kind", sa.String())
    operation = sa.column("operation_id", sa.Text())
    principal = sa.column("principal_id", sa.Uuid())
    principal_kind = sa.column("principal_kind", sa.String())
    action = sa.column("action_id", sa.String())
    cleanup = sa.column("cleanup_obligation_id", sa.Uuid())
    human = sa.and_(
        *(
            sa.column(name).is_(None)
            for name in ("human_authority", "human_subject", "human_version")
        )
    )
    product = sa.and_(
        kind == "product",
        operation.is_not(None),
        principal.is_not(None),
        principal_kind.is_not(None),
        action.is_not(None),
        cleanup.is_(None),
    )
    artifact = sa.and_(
        kind == "artifact_cleanup",
        cleanup.is_not(None),
        operation.is_(None),
        principal.is_(None),
        principal_kind.is_(None),
        action.is_(None),
        human,
    )
    if not deletion:
        return sa.or_(product, artifact)
    parent = sa.column("deletion_obligation_id", sa.Uuid())
    local = sa.and_(
        kind == "project_deletion",
        parent.is_not(None),
        cleanup.is_(None),
        operation.is_(None),
        principal.is_(None),
        principal_kind.is_(None),
        action.is_(None),
        human,
    )
    return sa.or_(sa.and_(product, parent.is_(None)), sa.and_(artifact, parent.is_(None)), local)


def upgrade() -> None:
    scope = [
        "operation_id",
        "installation_id",
        "organization_id",
        "project_id",
        "initiator_principal_id",
    ]
    op.create_unique_constraint(
        "uq_deletion_status_original_scope", "deletion_status_bindings", scope
    )
    op.create_table(
        "project_deletion_obligations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("job_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("operation_id", sa.Text(), nullable=False, unique=True),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("installation_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("initiator_principal_id", sa.Uuid(), nullable=False),
        sa.Column("request_key", sa.Text(), nullable=False),
        sa.Column("request_fingerprint", sa.LargeBinary(), nullable=False),
        sa.Column("before_access_revision", sa.BigInteger(), nullable=False),
        sa.Column("access_revision", sa.BigInteger(), nullable=False),
        sa.Column("admitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_revision", sa.BigInteger(), nullable=False),
        sa.Column("shutdown_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("physical_cleanup_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            scope,
            ["deletion_status_bindings." + name for name in scope],
            name="fk_project_deletion_original",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "id",
            "job_id",
            "request_id",
            "installation_id",
            "organization_id",
            "project_id",
            name="uq_project_deletion_child_scope",
        ),
        sa.CheckConstraint(
            sa.and_(
                sa.column("before_access_revision").between(0, 9007199254740990),
                sa.column("access_revision") == sa.column("before_access_revision") + 1,
            ),
            name="ck_project_deletion_revisions",
        ),
        sa.CheckConstraint(
            sa.column("source_revision").between(1, 9007199254740991),
            name="ck_project_deletion_source_revision",
        ),
        sa.CheckConstraint(
            sa.func.octet_length(sa.column("request_fingerprint")) == 32,
            name="ck_project_deletion_fingerprint",
        ),
        sa.CheckConstraint(
            sa.and_(
                sa.or_(
                    sa.column("shutdown_completed_at").is_(None),
                    sa.column("shutdown_completed_at") >= sa.column("admitted_at"),
                ),
                sa.or_(
                    sa.column("physical_cleanup_completed_at").is_(None),
                    sa.and_(
                        sa.column("shutdown_completed_at").is_not(None),
                        sa.column("physical_cleanup_completed_at")
                        >= sa.column("shutdown_completed_at"),
                    ),
                ),
            ),
            name="ck_project_deletion_progress",
        ),
    )
    op.create_index(
        "ix_project_deletion_physical_pending",
        "project_deletion_obligations",
        ["admitted_at", "id"],
        postgresql_where=sa.and_(
            sa.column("shutdown_completed_at").is_not(None),
            sa.column("physical_cleanup_completed_at").is_(None),
        ),
    )
    op.add_column("durable_jobs", sa.Column("deletion_obligation_id", sa.Uuid(), nullable=True))
    op.create_unique_constraint(
        "uq_job_project_deletion", "durable_jobs", ["deletion_obligation_id"]
    )
    op.create_foreign_key(
        "fk_job_project_deletion_scope",
        "durable_jobs",
        "project_deletion_obligations",
        [
            "deletion_obligation_id",
            "id",
            "request_id",
            "installation_id",
            "organization_id",
            "project_id",
        ],
        ["id", "job_id", "request_id", "installation_id", "organization_id", "project_id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint("ck_job_closed_binding", "durable_jobs", type_="check")
    op.create_check_constraint(
        "ck_job_closed_binding", "durable_jobs", _binding_shape(deletion=True)
    )


def downgrade() -> None:
    parents = sa.table("project_deletion_obligations", sa.column("id"))
    jobs = sa.table("durable_jobs", sa.column("binding_kind"))
    if op.get_bind().scalar(
        sa.select(sa.func.count()).select_from(parents)
    ) or op.get_bind().scalar(
        sa.select(sa.func.count())
        .select_from(jobs)
        .where(jobs.c.binding_kind == "project_deletion")
    ):
        raise RuntimeError("Retained Project deletion prevents this downgrade.")
    op.drop_constraint("ck_job_closed_binding", "durable_jobs", type_="check")
    op.create_check_constraint(
        "ck_job_closed_binding", "durable_jobs", _binding_shape(deletion=False)
    )
    op.drop_constraint("fk_job_project_deletion_scope", "durable_jobs", type_="foreignkey")
    op.drop_constraint("uq_job_project_deletion", "durable_jobs", type_="unique")
    op.drop_column("durable_jobs", "deletion_obligation_id")
    op.drop_index("ix_project_deletion_physical_pending", table_name="project_deletion_obligations")
    op.drop_table("project_deletion_obligations")
    op.drop_constraint(
        "uq_deletion_status_original_scope", "deletion_status_bindings", type_="unique"
    )
