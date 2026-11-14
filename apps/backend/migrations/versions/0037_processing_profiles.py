"""Store immutable Project Processing Profiles and their creator assignments."""

import sqlalchemy as sa
from alembic import op
from migrations.types import MigrationRevisionReference
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0037_processing_profiles"
down_revision: MigrationRevisionReference = "0036_provider_credentials"
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None

_PROFILES = "processing_profiles"
_GRANTS = "processing_profile_action_grants"
_RESULTS = "processing_profile_creation_results"
_ACTIONS = ("view-processing-profile", "use-processing-profile")
_MAX_REVISION = 2**53 - 1
_GRANT_RESULTS = "processing_profile_grant_operation_results"
_REPAIR_RESULTS = "stranded_authority_repair_receipts"
_GRANT_FAMILY = "processing_profile_grant_read"


def _lookup_constraint(*, profile_grants: bool) -> None:
    family, action, project, method = (
        sa.column("lookup_authority_family", sa.String()),
        sa.column("lookup_action_id", sa.String()),
        sa.column("project_id", sa.Uuid()),
        sa.column("method", sa.String()),
    )
    supported = sa.or_(
        sa.and_(family.in_(("project_action_use", "project_grant_read")), project.is_not(None)),
        sa.and_(family == "organization_action_use", project.is_(None)),
        sa.and_(
            family == "access_group_deletion",
            action == "delete-access-group",
            project.is_not(None),
            method == "DELETE",
        ),
        sa.and_(
            family == "organization_grant_read",
            action.in_(("admit-users", "suspend-users", "restore-users", "create-projects")),
            project.is_(None),
            method.in_(("PUT", "DELETE")),
        ),
        sa.and_(
            family == "access_group_grant_read",
            action.in_(("add-documents", "update-documents", "delete-documents")),
            project.is_not(None),
            method.in_(("PUT", "DELETE")),
        ),
        sa.and_(
            family == "application_account_grant_read",
            action.in_(
                ("issue-application-keys", "revoke-application-keys", "delete-application-account")
            ),
            project.is_not(None),
            method.in_(("PUT", "DELETE")),
        ),
    )
    supported = sa.or_(
        supported,
        sa.and_(
            family == "model_connection_grant_read",
            action.in_(
                (
                    "view-model-connection-configuration",
                    "use-model-connection",
                    "manage-model-connection",
                    "delete-model-connection",
                )
            ),
            project.is_not(None),
            method.in_(("PUT", "DELETE")),
        ),
    )
    if profile_grants:
        supported = sa.or_(
            supported,
            sa.and_(
                family == _GRANT_FAMILY,
                action.in_(_ACTIONS),
                project.is_not(None),
                method.in_(("PUT", "DELETE")),
            ),
        )
    op.drop_constraint("ck_idempotency_lookup_authority", "idempotency_reservations", type_="check")
    op.create_check_constraint(
        "ck_idempotency_lookup_authority",
        "idempotency_reservations",
        sa.or_(
            sa.and_(family.is_(None), action.is_(None)),
            sa.and_(
                family.is_not(None),
                action.is_not(None),
                sa.func.length(sa.func.trim(action)) > 0,
                supported,
            ),
        ),
    )


def _grant_receipts() -> None:
    before, after = (
        sa.column("before_revision", sa.BigInteger()),
        sa.column("access_revision", sa.BigInteger()),
    )
    old, level = sa.column("before_can_grant", sa.Boolean()), sa.column("can_grant", sa.Boolean())
    status = sa.column("status_code", sa.Integer())
    changed = old.is_distinct_from(level)
    created = sa.and_(old.is_(None), level.is_not(None))
    op.create_table(
        _GRANT_RESULTS,
        sa.Column("operation_id", sa.Text(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("processing_profile_id", sa.Uuid(), nullable=False),
        sa.Column("actor_principal_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_principal_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("before_can_grant", sa.Boolean(), nullable=True),
        sa.Column("can_grant", sa.Boolean(), nullable=True),
        sa.Column("before_revision", sa.BigInteger(), nullable=False),
        sa.Column("access_revision", sa.BigInteger(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["operation_id", "organization_id", "project_id", "actor_principal_id"],
            [
                "idempotency_reservations.operation_id",
                "idempotency_reservations.organization_id",
                "idempotency_reservations.project_id",
                "idempotency_reservations.principal_id",
            ],
            name="fk_processing_profile_grant_original_operation",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id", "processing_profile_id"],
            [
                "processing_profiles.organization_id",
                "processing_profiles.project_id",
                "processing_profiles.id",
            ],
            name="fk_processing_profile_grant_original_target",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "recipient_principal_id"],
            ["principals.organization_id", "principals.id"],
            name="fk_processing_profile_grant_original_recipient",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            sa.column("action", sa.String()).in_(_ACTIONS),
            name="ck_processing_profile_original_action",
        ),
        sa.CheckConstraint(
            sa.and_(
                before.between(0, _MAX_REVISION),
                after.between(0, _MAX_REVISION),
                after == before + sa.case((changed, 1), else_=0),
            ),
            name="ck_processing_profile_grant_original_revision",
        ),
        sa.CheckConstraint(
            status == sa.case((created, 201), else_=200),
            name="ck_processing_profile_grant_original_status",
        ),
    )


def _repair_constraint(*, profile_grants: bool) -> None:
    kind = sa.column("responsibility_kind", sa.String())
    target = sa.column("target_kind", sa.String())
    project = sa.column("project_id", sa.Uuid())
    group = sa.column("access_group_id", sa.Uuid())
    account = sa.column("application_account_id", sa.Uuid())
    action = sa.column("action_id", sa.String())
    project_actions = (
        "manage-project-members",
        "create-access-groups",
        "create-application-accounts",
        "create-pipelines",
        "create-deployments",
        "manage-upload-defaults",
        "delete-project",
        "inspect-budget",
        "manage-budget",
        "manage-trace-policy",
        "delete-trace-history",
        "inspect-feedback",
        "create-collections",
        "create-sources",
        "create-model-connections",
        "create-processing-profiles",
        "create-embedding-profiles",
    )
    previous = sa.or_(
        sa.and_(
            kind == "group-manager",
            target == "access-group",
            project.is_not(None),
            group.is_not(None),
            account.is_(None),
            action.is_(None),
        ),
        sa.and_(
            kind == "action-grantor",
            action.is_not(None),
            sa.or_(
                sa.and_(
                    target == "organization",
                    project.is_(None),
                    group.is_(None),
                    account.is_(None),
                    action.in_(
                        ("admit-users", "suspend-users", "restore-users", "create-projects")
                    ),
                ),
                sa.and_(
                    target == "project",
                    project.is_not(None),
                    group.is_(None),
                    account.is_(None),
                    action.in_(project_actions),
                ),
                sa.and_(
                    target == "access-group",
                    project.is_not(None),
                    group.is_not(None),
                    account.is_(None),
                    action.in_(("add-documents", "update-documents", "delete-documents")),
                ),
                sa.and_(
                    target == "application-account",
                    project.is_not(None),
                    group.is_(None),
                    account.is_not(None),
                    action.in_(
                        (
                            "issue-application-keys",
                            "revoke-application-keys",
                            "delete-application-account",
                        )
                    ),
                ),
            ),
        ),
    )
    table = _REPAIR_RESULTS
    op.drop_constraint("ck_stranded_repair_responsibility", table, type_="check")
    model = sa.column("model_connection_id", sa.Uuid())
    previous = sa.or_(
        sa.and_(previous, model.is_(None)),
        sa.and_(
            kind == "action-grantor",
            target == "model-connection",
            project.is_not(None),
            group.is_(None),
            account.is_(None),
            model.is_not(None),
            action.is_not(None),
            action.in_(
                (
                    "view-model-connection-configuration",
                    "use-model-connection",
                    "manage-model-connection",
                    "delete-model-connection",
                )
            ),
        ),
    )
    if profile_grants:
        profile = sa.column("processing_profile_id", sa.Uuid())
        previous = sa.or_(
            sa.and_(previous, profile.is_(None)),
            sa.and_(
                kind == "action-grantor",
                target == "processing-profile",
                project.is_not(None),
                group.is_(None),
                account.is_(None),
                model.is_(None),
                profile.is_not(None),
                action.is_not(None),
                action.in_(_ACTIONS),
            ),
        )
    op.create_check_constraint("ck_stranded_repair_responsibility", table, previous)


def upgrade() -> None:
    name = sa.column("name", sa.Text())
    op.create_table(
        _PROFILES,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("docling_slim_version", sa.String(32), nullable=False),
        sa.Column("docling_core_version", sa.String(32), nullable=False),
        sa.Column("asset_manifest_sha256", sa.String(64), nullable=False),
        sa.Column("max_content_tokens", sa.Integer(), nullable=False),
        sa.Column("merge_peers", sa.Boolean(), nullable=False),
        sa.Column("repeat_table_header", sa.Boolean(), nullable=False),
        sa.Column("ocr_enabled", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id"],
            ["projects.organization_id", "projects.id"],
            name="fk_processing_profiles_project",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("project_id", "name", name="uq_processing_profiles_project_name"),
        sa.UniqueConstraint("project_id", "id", name="uq_processing_profiles_project_id"),
        sa.UniqueConstraint(
            "organization_id", "project_id", "id", name="uq_processing_profiles_scope_id"
        ),
        sa.CheckConstraint(
            sa.and_(
                sa.func.length(name).between(1, 63),
                name.regexp_match("^[a-z]([a-z0-9-]*[a-z0-9])?$"),
            ),
            name="ck_processing_profiles_name",
        ),
        sa.CheckConstraint(
            sa.func.length(sa.column("display_name")).between(1, 128),
            name="ck_processing_profiles_display_name",
        ),
        sa.CheckConstraint(
            sa.and_(
                sa.func.length(sa.func.trim(sa.column("docling_slim_version"))).between(1, 32),
                sa.func.length(sa.func.trim(sa.column("docling_core_version"))).between(1, 32),
                sa.column("asset_manifest_sha256", sa.String()).regexp_match("^[0-9a-f]{64}$"),
                sa.column("max_content_tokens", sa.Integer()).between(1, 1024),
                sa.column("ocr_enabled", sa.Boolean()).is_(False),
            ),
            name="ck_processing_profiles_definition",
        ),
    )

    action = sa.column("action", sa.String())
    recipient_kind = sa.column("recipient_kind", sa.String())
    can_grant = sa.column("can_grant", sa.Boolean())
    op.create_table(
        _GRANTS,
        sa.Column("project_id", sa.Uuid(), primary_key=True),
        sa.Column("processing_profile_id", sa.Uuid(), primary_key=True),
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
            ["project_id", "processing_profile_id"],
            ["processing_profiles.project_id", "processing_profiles.id"],
            name="fk_processing_profile_grants_target",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "recipient_principal_id", "recipient_kind"],
            [
                "project_memberships.project_id",
                "project_memberships.principal_id",
                "project_memberships.principal_kind",
            ],
            name="fk_processing_profile_grants_recipient",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(action.in_(_ACTIONS), name="ck_processing_profile_grants_action"),
        sa.CheckConstraint(
            sa.or_(
                recipient_kind == "human",
                sa.and_(recipient_kind == "application", can_grant.is_(False)),
            ),
            name="ck_processing_profile_grants_recipient",
        ),
    )
    op.create_index(
        "ix_processing_profile_grants_recipient",
        _GRANTS,
        ["project_id", "recipient_principal_id", "action"],
    )

    before = sa.column("before_revision", sa.BigInteger())
    after = sa.column("project_access_revision", sa.BigInteger())
    op.create_table(
        _RESULTS,
        sa.Column("operation_id", sa.Text(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("creator_principal_id", sa.Uuid(), nullable=False),
        sa.Column("processing_profile_id", sa.Uuid(), nullable=False),
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
            name="fk_processing_profile_creation_operation",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id", "processing_profile_id"],
            [
                "processing_profiles.organization_id",
                "processing_profiles.project_id",
                "processing_profiles.id",
            ],
            name="fk_processing_profile_creation_target",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            sa.and_(before.between(0, _MAX_REVISION - 1), after == before + 1),
            name="ck_processing_profile_creation_revision",
        ),
        sa.CheckConstraint(
            sa.and_(
                sa.column("initial_actions", JSONB()) == sa.func.jsonb_build_array(*_ACTIONS),
                can_grant.is_(True),
            ),
            name="ck_processing_profile_creation_grants",
        ),
    )

    _lookup_constraint(profile_grants=True)
    _grant_receipts()
    op.add_column(_REPAIR_RESULTS, sa.Column("processing_profile_id", sa.Uuid()))
    _repair_constraint(profile_grants=True)


def downgrade() -> None:
    connection = op.get_bind()
    if any(
        connection.scalar(sa.select(sa.exists(sa.select(1).select_from(sa.table(name)))))
        for name in (_GRANT_RESULTS, _RESULTS, _GRANTS, _PROFILES)
    ):
        raise RuntimeError("Retained Processing Profiles, grants or originals prevent downgrade.")
    reservations = sa.table(
        "idempotency_reservations", sa.column("lookup_authority_family", sa.String())
    )
    if connection.scalar(
        sa.select(
            sa.exists(
                sa.select(1)
                .select_from(reservations)
                .where(reservations.c.lookup_authority_family == _GRANT_FAMILY)
            )
        )
    ):
        raise RuntimeError("Retained Processing Profile grant operations prevent downgrade.")
    repairs = sa.table(_REPAIR_RESULTS, sa.column("processing_profile_id", sa.Uuid()))
    if connection.scalar(
        sa.select(
            sa.exists(
                sa.select(1)
                .select_from(repairs)
                .where(repairs.c.processing_profile_id.is_not(None))
            )
        )
    ):
        raise RuntimeError("Retained Processing Profile repair originals prevent downgrade.")
    _repair_constraint(profile_grants=False)
    op.drop_column(_REPAIR_RESULTS, "processing_profile_id")
    _lookup_constraint(profile_grants=False)
    op.drop_table(_GRANT_RESULTS)
    op.drop_table(_RESULTS)
    op.drop_table(_GRANTS)
    op.drop_table(_PROFILES)
