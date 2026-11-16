"""Store immutable scoped Embedding Profiles and their creator assignments."""

import sqlalchemy as sa
from alembic import op
from migrations.types import MigrationRevisionReference
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0041_embedding_profiles"
down_revision: MigrationRevisionReference = "0040_model_dispatch_issuance"
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None

_PROFILES = "embedding_profiles"
_GRANTS = "embedding_profile_action_grants"
_RESULTS = "embedding_profile_creation_results"
_ACTIONS = ("view-embedding-profile", "use-embedding-profile")
_MAX_REVISION = 2**53 - 1


def _create_profiles() -> None:
    name = sa.column("name", sa.Text())
    first = sa.column("shard_zero_name", sa.String(63))
    second = sa.column("shard_one_name", sa.String(63))
    token_bound = sa.column("token_bound_kind", sa.String(32))
    op.create_table(
        _PROFILES,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("model_connection_id", sa.Uuid(), nullable=False),
        sa.Column("model_alias", sa.Text(), nullable=False),
        sa.Column("expected_provider", sa.Text(), nullable=False),
        sa.Column("expected_model_revision", sa.Text(), nullable=True),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("normalization", sa.String(32), nullable=False),
        sa.Column("distance", sa.String(32), nullable=False),
        sa.Column("document_prefix", sa.Text(), nullable=False),
        sa.Column("query_prefix", sa.Text(), nullable=False),
        sa.Column("context_tokens", sa.BigInteger(), nullable=False),
        sa.Column("token_bound_kind", sa.String(32), nullable=False),
        sa.Column("token_bound_implementation", sa.Text(), nullable=False),
        sa.Column("token_bound_revision", sa.Text(), nullable=False),
        sa.Column("settings_fingerprint", sa.String(64), nullable=False),
        sa.Column("vector_index_id", sa.Uuid(), nullable=False),
        sa.Column("vector_layout_id", sa.Uuid(), nullable=False),
        sa.Column("placement_version", sa.Integer(), nullable=False),
        sa.Column("shard_count", sa.Integer(), nullable=False),
        sa.Column("shard_zero_name", sa.String(63), nullable=False),
        sa.Column("shard_one_name", sa.String(63), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id"],
            ["projects.organization_id", "projects.id"],
            name="fk_embedding_profiles_project",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "model_connection_id"],
            ["model_connections.project_id", "model_connections.id"],
            name="fk_embedding_profiles_connection",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("project_id", "name", name="uq_embedding_profiles_project_name"),
        sa.UniqueConstraint("project_id", "id", name="uq_embedding_profiles_project_id"),
        sa.UniqueConstraint(
            "organization_id", "project_id", "id", name="uq_embedding_profiles_scope_id"
        ),
        sa.UniqueConstraint("vector_index_id", name="uq_embedding_profiles_index_id"),
        sa.UniqueConstraint("vector_layout_id", name="uq_embedding_profiles_layout_id"),
        sa.CheckConstraint(
            sa.and_(
                sa.func.length(name).between(1, 63),
                name.regexp_match("^[a-z]([a-z0-9-]*[a-z0-9])?$"),
                sa.func.length(sa.column("display_name")).between(1, 128),
            ),
            name="ck_embedding_profiles_names",
        ),
        sa.CheckConstraint(
            sa.and_(
                sa.column("dimensions", sa.Integer()).between(1, 1536),
                sa.column("context_tokens", sa.BigInteger()).between(1, _MAX_REVISION),
                sa.column("normalization", sa.String(32)).in_(("none", "l2")),
                sa.column("distance", sa.String(32)).in_(("cosine", "dot-product", "euclidean")),
                token_bound.in_(("exact", "conservative-upper-bound")),
                sa.column("settings_fingerprint", sa.String(64)).regexp_match("^[0-9a-f]{64}$"),
            ),
            name="ck_embedding_profiles_settings",
        ),
        sa.CheckConstraint(
            sa.and_(
                sa.column("placement_version", sa.Integer()) == 1,
                sa.column("shard_count", sa.Integer()) == 2,
                first.regexp_match("^im-v1-[a-z2-7]{52}$"),
                second.regexp_match("^im-v1-[a-z2-7]{52}$"),
                first != second,
            ),
            name="ck_embedding_profiles_shards",
        ),
    )
    op.create_index(
        "ix_embedding_profiles_connection", _PROFILES, ["project_id", "model_connection_id"]
    )


def _create_grants() -> None:
    recipient_kind = sa.column("recipient_kind", sa.String())
    can_grant = sa.column("can_grant", sa.Boolean())
    op.create_table(
        _GRANTS,
        sa.Column("project_id", sa.Uuid(), primary_key=True),
        sa.Column("embedding_profile_id", sa.Uuid(), primary_key=True),
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
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "embedding_profile_id"],
            ["embedding_profiles.project_id", "embedding_profiles.id"],
            name="fk_embedding_profile_grants_target",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "recipient_principal_id", "recipient_kind"],
            [
                "project_memberships.project_id",
                "project_memberships.principal_id",
                "project_memberships.principal_kind",
            ],
            name="fk_embedding_profile_grants_recipient",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            sa.column("action", sa.String()).in_(_ACTIONS),
            name="ck_embedding_profile_grants_action",
        ),
        sa.CheckConstraint(
            sa.or_(
                recipient_kind == "human",
                sa.and_(recipient_kind == "application", can_grant.is_(False)),
            ),
            name="ck_embedding_profile_grants_recipient",
        ),
    )
    op.create_index(
        "ix_embedding_profile_grants_recipient",
        _GRANTS,
        ["project_id", "recipient_principal_id", "action"],
    )


def _create_originals() -> None:
    before = sa.column("before_revision", sa.BigInteger())
    after = sa.column("project_access_revision", sa.BigInteger())
    op.create_table(
        _RESULTS,
        sa.Column("operation_id", sa.Text(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("creator_principal_id", sa.Uuid(), nullable=False),
        sa.Column("embedding_profile_id", sa.Uuid(), nullable=False),
        sa.Column("before_revision", sa.BigInteger(), nullable=False),
        sa.Column("project_access_revision", sa.BigInteger(), nullable=False),
        sa.Column("initial_actions", JSONB(), nullable=False),
        sa.Column("can_grant", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["operation_id", "organization_id", "project_id", "creator_principal_id"],
            [
                "idempotency_reservations.operation_id",
                "idempotency_reservations.organization_id",
                "idempotency_reservations.project_id",
                "idempotency_reservations.principal_id",
            ],
            name="fk_embedding_profile_creation_operation",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id", "embedding_profile_id"],
            [
                "embedding_profiles.organization_id",
                "embedding_profiles.project_id",
                "embedding_profiles.id",
            ],
            name="fk_embedding_profile_creation_target",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            sa.and_(before.between(0, _MAX_REVISION - 1), after == before + 1),
            name="ck_embedding_profile_creation_revision",
        ),
        sa.CheckConstraint(
            sa.and_(
                sa.column("initial_actions", JSONB()) == sa.func.jsonb_build_array(*_ACTIONS),
                sa.column("can_grant", sa.Boolean()).is_(True),
            ),
            name="ck_embedding_profile_creation_grants",
        ),
    )


def upgrade() -> None:
    _create_profiles()
    _create_grants()
    _create_originals()


def downgrade() -> None:
    connection = op.get_bind()
    if any(
        connection.scalar(sa.select(sa.exists(sa.select(1).select_from(sa.table(name)))))
        for name in (_RESULTS, _GRANTS, _PROFILES)
    ):
        raise RuntimeError("Retained Embedding Profiles, grants or originals prevent downgrade.")

    op.drop_table(_RESULTS)
    op.drop_table(_GRANTS)
    op.drop_table(_PROFILES)
