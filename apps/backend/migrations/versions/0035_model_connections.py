"""Store exact Project model connections, assignments, and original creation receipts."""

import sqlalchemy as sa
from alembic import op
from migrations.types import MigrationRevisionReference
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0035_model_connections"
down_revision: MigrationRevisionReference = "0034_human_lifecycle"
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None

_ACTIONS = (
    "view-model-connection-configuration",
    "use-model-connection",
    "manage-model-connection",
    "delete-model-connection",
)
_MAX_REVISION = 9007199254740991


_GRANT_FAMILY = "model_connection_grant_read"


def _lookup_constraint(*, model_grants: bool) -> None:
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
    if model_grants:
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
        "model_connection_grant_operation_results",
        sa.Column("operation_id", sa.Text(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("model_connection_id", sa.Uuid(), nullable=False),
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
            name="fk_model_connection_grant_original_operation",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "model_connection_id"],
            ["model_connections.project_id", "model_connections.id"],
            name="fk_model_connection_grant_original_target",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "recipient_principal_id"],
            ["principals.organization_id", "principals.id"],
            name="fk_model_connection_grant_original_recipient",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            sa.column("action", sa.String()).in_(_ACTIONS),
            name="ck_model_connection_original_action",
        ),
        sa.CheckConstraint(
            sa.and_(
                before.between(0, _MAX_REVISION),
                after.between(0, _MAX_REVISION),
                after == before + sa.case((changed, 1), else_=0),
            ),
            name="ck_model_connection_grant_original_revision",
        ),
        sa.CheckConstraint(
            status == sa.case((created, 201), else_=200),
            name="ck_model_connection_grant_original_status",
        ),
    )


def _set_repair_constraint(*, model_grants: bool) -> None:
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
    table = "stranded_authority_repair_receipts"
    op.drop_constraint("ck_stranded_repair_responsibility", table, type_="check")
    if model_grants:
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
                action.in_(_ACTIONS),
            ),
        )
    op.create_check_constraint("ck_stranded_repair_responsibility", table, previous)


def upgrade() -> None:
    provider, authentication = (
        sa.column("provider", sa.String()),
        sa.column("authentication", sa.String()),
    )
    name = sa.column("name", sa.Text())
    op.create_table(
        "model_connections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("api_version", sa.Text(), nullable=True),
        sa.Column("authentication", sa.String(32), nullable=False),
        sa.Column("access_revision", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("project_id", "name", name="uq_model_connections_project_name"),
        sa.UniqueConstraint("project_id", "id", name="uq_model_connections_project_id"),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id"],
            ["projects.organization_id", "projects.id"],
            name="fk_model_connections_project",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            sa.and_(
                sa.func.length(name).between(1, 63), name.op("~")("^[a-z]([a-z0-9-]*[a-z0-9])?$")
            ),
            name="ck_model_connections_name",
        ),
        sa.CheckConstraint(
            sa.func.length(sa.column("display_name")).between(1, 128),
            name="ck_model_connections_display_name",
        ),
        sa.CheckConstraint(
            sa.func.length(sa.column("base_url")).between(1, 2048),
            name="ck_model_connections_base_url",
        ),
        sa.CheckConstraint(
            sa.or_(
                sa.and_(provider.in_(("openai", "openai-compatible")), authentication == "api-key"),
                sa.and_(provider == "ollama", authentication == "none"),
            ),
            name="ck_model_connections_authentication",
        ),
        sa.CheckConstraint(
            sa.column("access_revision").between(0, _MAX_REVISION),
            name="ck_model_connections_access_revision",
        ),
    )

    recipient, action = sa.column("recipient_kind", sa.String()), sa.column("action", sa.String())
    op.create_table(
        "model_connection_action_grants",
        sa.Column("project_id", sa.Uuid(), primary_key=True),
        sa.Column("model_connection_id", sa.Uuid(), primary_key=True),
        sa.Column("recipient_principal_id", sa.Uuid(), primary_key=True),
        sa.Column("recipient_kind", sa.String(20), nullable=False),
        sa.Column("action", sa.String(100), primary_key=True),
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
            ["project_id", "model_connection_id"],
            ["model_connections.project_id", "model_connections.id"],
            name="fk_model_connection_grants_target",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "recipient_principal_id", "recipient_kind"],
            [
                "project_memberships.project_id",
                "project_memberships.principal_id",
                "project_memberships.principal_kind",
            ],
            name="fk_model_connection_grants_recipient",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(action.in_(_ACTIONS), name="ck_model_connection_grants_action"),
        sa.CheckConstraint(
            sa.or_(
                recipient == "human",
                sa.and_(
                    recipient == "application",
                    sa.column("can_grant").is_(False),
                    action.in_(_ACTIONS[:2]),
                ),
            ),
            name="ck_model_connection_grants_recipient",
        ),
    )
    op.create_index(
        "ix_model_connection_grants_recipient",
        "model_connection_action_grants",
        ["project_id", "recipient_principal_id", "action"],
    )

    before, after = (
        sa.column("before_revision", sa.BigInteger()),
        sa.column("project_access_revision", sa.BigInteger()),
    )
    op.create_table(
        "model_connection_creation_results",
        sa.Column("operation_id", sa.Text(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("creator_principal_id", sa.Uuid(), nullable=False),
        sa.Column("model_connection_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("api_version", sa.Text(), nullable=True),
        sa.Column("authentication", sa.String(32), nullable=False),
        sa.Column("before_revision", sa.BigInteger(), nullable=False),
        sa.Column("project_access_revision", sa.BigInteger(), nullable=False),
        sa.Column("initial_actions", JSONB(), nullable=False),
        sa.ForeignKeyConstraint(
            ["operation_id", "organization_id", "project_id", "creator_principal_id"],
            [
                "idempotency_reservations.operation_id",
                "idempotency_reservations.organization_id",
                "idempotency_reservations.project_id",
                "idempotency_reservations.principal_id",
            ],
            name="fk_model_connection_creation_operation",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "model_connection_id"],
            ["model_connections.project_id", "model_connections.id"],
            name="fk_model_connection_creation_target",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            sa.and_(before.between(0, _MAX_REVISION - 1), after == before + 1),
            name="ck_model_connection_creation_revisions",
        ),
    )

    _lookup_constraint(model_grants=True)
    _grant_receipts()
    op.add_column("stranded_authority_repair_receipts", sa.Column("model_connection_id", sa.Uuid()))
    _set_repair_constraint(model_grants=True)


def downgrade() -> None:
    owned_tables = (
        "model_connection_grant_operation_results",
        "model_connection_creation_results",
        "model_connection_action_grants",
        "model_connections",
    )
    connection = op.get_bind()
    # The controlled migration procedure stops application writers before downgrade.
    if any(
        connection.scalar(sa.select(sa.exists(sa.select(1).select_from(sa.table(name)))))
        for name in owned_tables
    ):
        raise RuntimeError(
            "Retained model connections, assignments, or original results prevent this downgrade."
        )
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
        raise RuntimeError("Retained model connection grant operations prevent this downgrade.")
    repairs = sa.table(
        "stranded_authority_repair_receipts", sa.column("model_connection_id", sa.Uuid())
    )
    if connection.scalar(
        sa.select(
            sa.exists(
                sa.select(1).select_from(repairs).where(repairs.c.model_connection_id.is_not(None))
            )
        )
    ):
        raise RuntimeError("Retained model connection repair originals prevent this downgrade.")
    _set_repair_constraint(model_grants=False)
    op.drop_column("stranded_authority_repair_receipts", "model_connection_id")
    _lookup_constraint(model_grants=False)
    for name in owned_tables:
        op.drop_table(name)
