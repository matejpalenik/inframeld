"""Retain exact Access-owned grant outcomes without binding them to live assignments."""

import sqlalchemy as sa
from alembic import op
from migrations.types import MigrationRevisionReference
from sqlalchemy.schema import SchemaItem

revision: str = "0026_access_action_grant_results"
down_revision: MigrationRevisionReference = "0025_access_group_administration"
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None

_MAX_REVISION = 9007199254740991
_ORGANIZATION_ACTIONS = ("admit-users", "suspend-users", "restore-users", "create-projects")
_GROUP_ACTIONS = ("add-documents", "update-documents", "delete-documents")
_APPLICATION_ACTIONS = (
    "issue-application-keys",
    "revoke-application-keys",
    "delete-application-account",
)
_NEW_FAMILIES = (
    "organization_grant_read",
    "access_group_grant_read",
    "application_account_grant_read",
)
_RESULT_TABLES = (
    "organization_action_grant_operation_results",
    "group_action_grant_operation_results",
    "application_action_grant_operation_results",
)


def _lookup_constraint(*, grants: bool) -> sa.ColumnElement[bool]:
    family, action, project, method = (
        sa.column("lookup_authority_family"),
        sa.column("lookup_action_id"),
        sa.column("project_id"),
        sa.column("method"),
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
    )
    if grants:
        supported = sa.or_(
            supported,
            sa.and_(
                family == "organization_grant_read",
                action.in_(_ORGANIZATION_ACTIONS),
                project.is_(None),
                method.in_(("PUT", "DELETE")),
            ),
            sa.and_(
                family == "access_group_grant_read",
                action.in_(_GROUP_ACTIONS),
                project.is_not(None),
                method.in_(("PUT", "DELETE")),
            ),
            sa.and_(
                family == "application_account_grant_read",
                action.in_(_APPLICATION_ACTIONS),
                project.is_not(None),
                method.in_(("PUT", "DELETE")),
            ),
        )
    return sa.or_(
        sa.and_(family.is_(None), action.is_(None)),
        sa.and_(
            family.is_not(None),
            action.is_not(None),
            sa.func.length(sa.func.trim(action)) > 0,
            supported,
        ),
    )


def _create_results(
    name: str,
    prefix: str,
    actions: tuple[str, ...],
    *,
    target_column: str | None,
) -> None:
    """Share the same receipt invariants across the three concrete Access tables."""
    before = sa.column("before_revision", sa.BigInteger())
    after = sa.column("access_revision", sa.BigInteger())
    previous = sa.column("before_can_grant", sa.Boolean())
    level = sa.column("can_grant", sa.Boolean())
    changed = sa.column("changed", sa.Boolean())
    method = sa.column("method", sa.String())
    status = sa.column("status_code", sa.Integer())
    scoped: list[SchemaItem] = []
    if target_column is not None:
        scoped = [
            sa.Column("project_id", sa.Uuid(), nullable=False),
            sa.Column(target_column, sa.Uuid(), nullable=False),
            sa.ForeignKeyConstraint(
                ["organization_id", "project_id"],
                ["projects.organization_id", "projects.id"],
                name=f"fk_{prefix}_project",
                ondelete="RESTRICT",
            ),
        ]
    operation_fields = ["operation_id", "organization_id", "actor_principal_id"]
    reservation_fields = ["operation_id", "organization_id", "principal_id"]
    if target_column is not None:
        operation_fields.insert(2, "project_id")
        reservation_fields.insert(2, "project_id")
    op.create_table(
        name,
        sa.Column("operation_id", sa.Text(), primary_key=True),
        sa.Column("installation_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        *scoped,
        sa.Column("actor_principal_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_principal_id", sa.Uuid(), nullable=False),
        sa.Column("action_id", sa.String(100), nullable=False),
        sa.Column("method", sa.String(6), nullable=False),
        sa.Column("before_revision", sa.BigInteger(), nullable=False),
        sa.Column("access_revision", sa.BigInteger(), nullable=False),
        sa.Column("before_can_grant", sa.Boolean(), nullable=True),
        sa.Column("can_grant", sa.Boolean(), nullable=True),
        sa.Column("changed", sa.Boolean(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["installation_id"],
            ["installation_identity.installation_id"],
            name=f"fk_{prefix}_installation",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            operation_fields,
            [f"idempotency_reservations.{field}" for field in reservation_fields],
            name=f"fk_{prefix}_operation",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "recipient_principal_id"],
            ["principals.organization_id", "principals.id"],
            name=f"fk_{prefix}_recipient",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            sa.column("action_id", sa.String()).in_(actions), name=f"ck_{prefix}_action"
        ),
        sa.CheckConstraint(method.in_(("PUT", "DELETE")), name=f"ck_{prefix}_method"),
        sa.CheckConstraint(
            sa.and_(before.between(0, _MAX_REVISION), after.between(0, _MAX_REVISION)),
            name=f"ck_{prefix}_revisions",
        ),
        sa.CheckConstraint(
            sa.or_(
                sa.and_(method == "PUT", level.is_not(None)),
                sa.and_(method == "DELETE", level.is_(None)),
            ),
            name=f"ck_{prefix}_level",
        ),
        sa.CheckConstraint(
            changed == previous.is_distinct_from(level), name=f"ck_{prefix}_changed"
        ),
        sa.CheckConstraint(
            sa.or_(
                sa.and_(changed.is_(True), after > before, after - before == 1),
                sa.and_(changed.is_(False), after == before),
            ),
            name=f"ck_{prefix}_revision_change",
        ),
        sa.CheckConstraint(
            sa.or_(
                sa.and_(method == "PUT", previous.is_(None), status == 201),
                sa.and_(sa.or_(method == "DELETE", previous.is_not(None)), status == 200),
            ),
            name=f"ck_{prefix}_original_status",
        ),
    )


def upgrade() -> None:
    op.drop_constraint("ck_idempotency_lookup_authority", "idempotency_reservations", type_="check")
    op.create_check_constraint(
        "ck_idempotency_lookup_authority",
        "idempotency_reservations",
        _lookup_constraint(grants=True),
    )
    _create_results(
        _RESULT_TABLES[0], "org_grant_result", _ORGANIZATION_ACTIONS, target_column=None
    )
    _create_results(
        _RESULT_TABLES[1], "group_grant_result", _GROUP_ACTIONS, target_column="group_id"
    )
    _create_results(
        _RESULT_TABLES[2],
        "application_grant_result",
        _APPLICATION_ACTIONS,
        target_column="application_principal_id",
    )


def downgrade() -> None:
    reservations = sa.table("idempotency_reservations", sa.column("lookup_authority_family"))
    if op.get_bind().scalar(
        sa.select(sa.func.count())
        .select_from(reservations)
        .where(reservations.c.lookup_authority_family.in_(_NEW_FAMILIES))
    ):
        raise RuntimeError("Retained Access grant operations prevent this downgrade.")
    for name in _RESULT_TABLES:
        if op.get_bind().scalar(sa.select(sa.func.count()).select_from(sa.table(name))):
            raise RuntimeError("Retained Access grant results prevent this downgrade.")
    for name in reversed(_RESULT_TABLES):
        op.drop_table(name)
    op.drop_constraint("ck_idempotency_lookup_authority", "idempotency_reservations", type_="check")
    op.create_check_constraint(
        "ck_idempotency_lookup_authority",
        "idempotency_reservations",
        _lookup_constraint(grants=False),
    )
