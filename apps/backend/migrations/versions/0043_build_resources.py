"""Persist saved Build resources and their exact Project relationships."""

from uuid import UUID

import sqlalchemy as sa
from alembic import op
from migrations.types import MigrationRevisionReference
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0043_build_resources"
down_revision: MigrationRevisionReference = "0042_document_erasure_fence"
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None

_SCOPE = ("installation_id", "organization_id", "project_id")
_PROJECT = ("organization_id", "project_id")
_COLLECTION_ACTIONS = ("view-collection", "edit-collection", "delete-collection")
_PIPELINE_ACTIONS = (
    "query",
    "inspect-query-traces",
    "build-pipeline",
    "view-pipeline-configuration",
    "edit-pipeline-configuration",
    "delete-pipeline",
    "generate-evaluation-cases",
    "view-evaluation-cases",
    "edit-evaluation-cases",
    "review-evaluation-cases",
    "run-evaluation",
    "inspect-evaluation-results",
    "manage-evaluation-case-audiences",
)


def _scope_columns() -> tuple[sa.Column[UUID], ...]:
    return tuple(sa.Column(name, sa.Uuid(), nullable=False) for name in _SCOPE)


def _references(table: str, columns: tuple[str, ...]) -> list[str]:
    return [f"{table}.{column}" for column in columns]


def _grants(resource: str, target: str, actions: tuple[str, ...]) -> None:
    table = f"{resource}_action_grants"
    target_id = f"{resource}_id"
    action = sa.column("action", sa.String())
    kind = sa.column("recipient_kind", sa.String())
    can_grant = sa.column("can_grant", sa.Boolean())
    eligible_application = sa.and_(kind == "application", can_grant.is_(False))
    if resource == "pipeline":
        eligible_application = sa.and_(
            eligible_application, action != "manage-evaluation-case-audiences"
        )
    op.create_table(
        table,
        sa.Column("project_id", sa.Uuid(), primary_key=True),
        sa.Column(target_id, sa.Uuid(), primary_key=True),
        sa.Column("recipient_principal_id", sa.Uuid(), primary_key=True),
        sa.Column("action", sa.String(100), primary_key=True),
        sa.Column("recipient_kind", sa.String(20), nullable=False),
        sa.Column("can_grant", sa.Boolean(), nullable=False),
        sa.Column(
            "assigned_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "assigned_by_principal_id",
            sa.Uuid(),
            sa.ForeignKey("principals.id", ondelete="SET NULL"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id", target_id],
            [f"{target}.project_id", f"{target}.id"],
            name=f"fk_{resource}_grants_target",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "recipient_principal_id", "recipient_kind"],
            _references("project_memberships", ("project_id", "principal_id", "principal_kind")),
            name=f"fk_{resource}_grants_recipient",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(action.in_(actions), name=f"ck_{resource}_grants_action"),
        sa.CheckConstraint(
            sa.or_(kind == "human", eligible_application), name=f"ck_{resource}_grants_recipient"
        ),
    )


def _collections() -> None:
    op.create_table(
        "collections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        *_scope_columns(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("current_revision_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            list(_PROJECT),
            ["projects.organization_id", "projects.id"],
            name="fk_collection_project",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("project_id", "name", name="uq_collections_project_name"),
        sa.UniqueConstraint("project_id", "id", name="uq_collections_project_id"),
        sa.UniqueConstraint(*_SCOPE, "id", name="uq_collections_scope_id"),
    )
    op.create_table(
        "collection_revisions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        *_scope_columns(),
        sa.Column("collection_id", sa.Uuid(), nullable=False),
        sa.Column("base_revision_id", sa.Uuid()),
        sa.Column("operation_id", sa.Text(), nullable=False, unique=True),
        sa.Column("actor_principal_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(*_SCOPE, "id", name="uq_collection_revisions_scope_id"),
        sa.UniqueConstraint("collection_id", "id", name="uq_collection_revisions_collection_id"),
        sa.ForeignKeyConstraint(
            [*_SCOPE, "collection_id"],
            _references("collections", (*_SCOPE, "id")),
            name="fk_collection_revisions_collection",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["collection_id", "base_revision_id"],
            ["collection_revisions.collection_id", "collection_revisions.id"],
            name="fk_collection_revisions_base",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            sa.column("base_revision_id").is_distinct_from(sa.column("id")),
            name="ck_collection_revision_base",
        ),
    )
    op.create_foreign_key(
        "fk_collection_current_revision",
        "collections",
        "collection_revisions",
        ["id", "current_revision_id"],
        ["collection_id", "id"],
        deferrable=True,
        initially="DEFERRED",
    )
    op.create_unique_constraint(
        "uq_document_versions_scope_document", "document_versions", [*_SCOPE, "document_id", "id"]
    )
    op.create_table(
        "collection_revision_documents",
        sa.Column("collection_revision_id", sa.Uuid(), primary_key=True),
        sa.Column("document_id", sa.Uuid(), primary_key=True),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        *_scope_columns(),
        sa.ForeignKeyConstraint(
            [*_SCOPE, "collection_revision_id"],
            _references("collection_revisions", (*_SCOPE, "id")),
            name="fk_collection_documents_revision",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [*_SCOPE, "document_id", "document_version_id"],
            _references("document_versions", (*_SCOPE, "document_id", "id")),
            name="fk_collection_documents_source",
            ondelete="RESTRICT",
        ),
    )
    _grants("collection", "collections", _COLLECTION_ACTIONS)


def _pipelines() -> None:
    op.create_table(
        "pipelines",
        sa.Column("id", sa.Uuid(), primary_key=True),
        *_scope_columns(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("current_revision", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            list(_PROJECT),
            ["projects.organization_id", "projects.id"],
            name="fk_pipeline_project",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("project_id", "name", name="uq_pipelines_project_name"),
        sa.UniqueConstraint("project_id", "id", name="uq_pipelines_project_id"),
        sa.UniqueConstraint(*_SCOPE, "id", name="uq_pipelines_scope_id"),
    )
    op.create_table(
        "pipeline_configuration_revisions",
        sa.Column("pipeline_id", sa.Uuid(), primary_key=True),
        sa.Column("revision", sa.BigInteger(), primary_key=True),
        *_scope_columns(),
        sa.Column("collection_id", sa.Uuid(), nullable=False),
        sa.Column("processing_profile_id", sa.Uuid(), nullable=False),
        sa.Column("embedding_profile_id", sa.Uuid(), nullable=False),
        sa.Column("model_connection_id", sa.Uuid(), nullable=False),
        sa.Column("model_alias", sa.Text(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("reranker", sa.Text(), nullable=False),
        sa.Column("top_k", sa.BigInteger(), nullable=False),
        sa.Column("max_passages", sa.BigInteger(), nullable=False),
        sa.Column("output_tokens", sa.BigInteger(), nullable=False),
        sa.Column("created_by_principal_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            *_SCOPE, "pipeline_id", "revision", name="uq_pipeline_configs_scope_id"
        ),
        sa.ForeignKeyConstraint(
            [*_SCOPE, "pipeline_id"],
            _references("pipelines", (*_SCOPE, "id")),
            name="fk_pipeline_configs_pipeline",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [*_SCOPE, "collection_id"],
            _references("collections", (*_SCOPE, "id")),
            name="fk_pipeline_configs_collection",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [*_PROJECT, "processing_profile_id"],
            _references("processing_profiles", ("organization_id", "project_id", "id")),
            name="fk_pipeline_configs_processing_profile",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [*_PROJECT, "embedding_profile_id"],
            _references("embedding_profiles", ("organization_id", "project_id", "id")),
            name="fk_pipeline_configs_embedding_profile",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "model_connection_id"],
            ["model_connections.project_id", "model_connections.id"],
            name="fk_pipeline_configs_model_connection",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            sa.and_(
                sa.column("revision", sa.BigInteger()) > 0,
                sa.column("max_passages", sa.BigInteger()) > 0,
                sa.column("top_k", sa.BigInteger()) >= sa.column("max_passages", sa.BigInteger()),
                sa.column("output_tokens", sa.BigInteger()) > 0,
            ),
            name="ck_pipeline_configs_limits",
        ),
    )
    op.create_foreign_key(
        "fk_pipeline_current_revision",
        "pipelines",
        "pipeline_configuration_revisions",
        ["id", "current_revision"],
        ["pipeline_id", "revision"],
        deferrable=True,
        initially="DEFERRED",
    )
    _grants("pipeline", "pipelines", _PIPELINE_ACTIONS)
    before = sa.column("before_revision", sa.BigInteger())
    after = sa.column("project_access_revision", sa.BigInteger())
    op.create_table(
        "pipeline_creation_results",
        sa.Column("operation_id", sa.Text(), primary_key=True),
        *_scope_columns(),
        sa.Column("creator_principal_id", sa.Uuid(), nullable=False),
        sa.Column("pipeline_id", sa.Uuid(), nullable=False),
        sa.Column("configuration_revision", sa.BigInteger(), nullable=False),
        sa.Column("before_revision", sa.BigInteger(), nullable=False),
        sa.Column("project_access_revision", sa.BigInteger(), nullable=False),
        sa.Column("initial_actions", JSONB(), nullable=False),
        sa.Column("can_grant", sa.Boolean(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["operation_id", "organization_id", "project_id", "creator_principal_id"],
            _references(
                "idempotency_reservations",
                ("operation_id", "organization_id", "project_id", "principal_id"),
            ),
            name="fk_pipeline_creation_original_operation",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            [*_SCOPE, "pipeline_id", "configuration_revision"],
            _references("pipeline_configuration_revisions", (*_SCOPE, "pipeline_id", "revision")),
            name="fk_pipeline_original_config",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            sa.and_(before >= 0, after == before + 1, after <= 2**53 - 1),
            name="ck_pipeline_creation_revision",
        ),
    )


def upgrade() -> None:
    _collections()
    _pipelines()
    op.create_table(
        "deployments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        *_scope_columns(),
        sa.Column("pipeline_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            list(_PROJECT),
            ["projects.organization_id", "projects.id"],
            name="fk_deployment_project",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [*_SCOPE, "pipeline_id"],
            _references("pipelines", (*_SCOPE, "id")),
            name="fk_deployment_pipeline",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_deployments_pipeline", "deployments", [*_SCOPE, "pipeline_id"])


def downgrade() -> None:
    connection = op.get_bind()
    if connection.get_isolation_level() != "READ COMMITTED":
        raise RuntimeError("Build resources downgrade requires READ COMMITTED.")

    # Transactional ALTER locks the owner tables before checking that none hold data.
    op.drop_constraint("fk_deployment_project", "deployments", type_="foreignkey")
    op.drop_constraint("fk_pipeline_current_revision", "pipelines", type_="foreignkey")
    op.drop_constraint("fk_collection_current_revision", "collections", type_="foreignkey")
    for table in ("deployments", "pipelines", "collections"):
        if (
            connection.scalar(sa.select(sa.literal(1)).select_from(sa.table(table)).limit(1))
            is not None
        ):
            raise RuntimeError("Retained Build resources block schema downgrade.")

    op.drop_table("deployments")
    op.drop_table("pipeline_creation_results")
    op.drop_table("pipeline_action_grants")
    op.drop_table("pipeline_configuration_revisions")
    op.drop_table("pipelines")
    op.drop_table("collection_action_grants")
    op.drop_table("collection_revision_documents")
    op.drop_table("collection_revisions")
    op.drop_table("collections")
    op.drop_constraint("uq_document_versions_scope_document", "document_versions", type_="unique")
