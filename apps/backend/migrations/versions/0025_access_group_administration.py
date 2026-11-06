"""Retain group selectors and original administration results after relationships disappear."""

import sqlalchemy as sa
from alembic import op
from migrations.types import MigrationRevisionReference
from sqlalchemy.schema import SchemaItem

revision: str = "0025_access_group_administration"
down_revision: MigrationRevisionReference = "0024_application_accounts"
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None
_MAX_REVISION = 9007199254740991


def _lookup_constraint(*, groups: bool) -> sa.ColumnElement[bool]:
    family, action, project, method = (
        sa.column("lookup_authority_family"),
        sa.column("lookup_action_id"),
        sa.column("project_id"),
        sa.column("method"),
    )
    supported = sa.or_(
        sa.and_(family.in_(("project_action_use", "project_grant_read")), project.is_not(None)),
        sa.and_(family == "organization_action_use", project.is_(None)),
    )
    if groups:
        supported = sa.or_(
            supported,
            sa.and_(
                family == "access_group_deletion",
                action == "delete-access-group",
                project.is_not(None),
                method == "DELETE",
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


def _result_columns() -> list[SchemaItem]:
    return [
        sa.Column("operation_id", sa.Text(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("actor_principal_id", sa.Uuid(), nullable=False),
        sa.Column("before_revision", sa.BigInteger(), nullable=False),
        sa.Column("access_revision", sa.BigInteger(), nullable=False),
    ]


def _operation_fk(name: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["operation_id", "organization_id", "project_id", "actor_principal_id"],
        [
            "idempotency_reservations.operation_id",
            "idempotency_reservations.organization_id",
            "idempotency_reservations.project_id",
            "idempotency_reservations.principal_id",
        ],
        name=name,
        ondelete="CASCADE",
    )


def upgrade() -> None:
    op.drop_constraint("ck_idempotency_lookup_authority", "idempotency_reservations", type_="check")
    op.create_check_constraint(
        "ck_idempotency_lookup_authority",
        "idempotency_reservations",
        _lookup_constraint(groups=True),
    )
    op.add_column("access_groups", sa.Column("resource_name", sa.Text(), nullable=True))
    name = sa.column("resource_name")
    op.create_check_constraint(
        "ck_access_group_name",
        "access_groups",
        sa.or_(
            name.is_(None),
            sa.and_(
                sa.func.length(name).between(1, 63), name.op("~")("^[a-z]([a-z0-9-]*[a-z0-9])?$")
            ),
        ),
    )
    op.create_unique_constraint(
        "uq_access_group_name", "access_groups", ["project_id", "resource_name"]
    )
    op.create_table(
        "access_group_name_reservations",
        sa.Column("project_id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.Text(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("retired", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("project_id", "group_id", name="uq_access_group_reserved_identity"),
        sa.UniqueConstraint(
            "project_id", "name", "group_id", name="uq_access_group_reserved_binding"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id"],
            ["projects.organization_id", "projects.id"],
            name="fk_access_group_name_project",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            sa.and_(
                sa.func.length(sa.column("name")).between(1, 63),
                sa.column("name").op("~")("^[a-z]([a-z0-9-]*[a-z0-9])?$"),
            ),
            name="ck_access_group_reserved_name",
        ),
    )
    op.create_foreign_key(
        "fk_access_group_reserved_name",
        "access_groups",
        "access_group_name_reservations",
        ["project_id", "resource_name", "id"],
        ["project_id", "name", "group_id"],
        ondelete="RESTRICT",
    )
    before, after = sa.column("before_revision"), sa.column("access_revision")
    revisions = sa.and_(before >= 0, before <= _MAX_REVISION, after >= 0, after <= _MAX_REVISION)
    op.create_table(
        "access_group_creation_results",
        *_result_columns(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        _operation_fk("fk_access_group_creation_operation"),
        sa.ForeignKeyConstraint(
            ["project_id", "name", "group_id"],
            [
                "access_group_name_reservations.project_id",
                "access_group_name_reservations.name",
                "access_group_name_reservations.group_id",
            ],
            name="fk_access_group_creation_name",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            sa.and_(revisions, after - before == 1), name="ck_access_group_creation_revisions"
        ),
    )
    bm, bg, am, ag, changed, kind, status = (
        sa.column(n)
        for n in (
            "before_member",
            "before_manager",
            "member",
            "manager",
            "changed",
            "change_kind",
            "status_code",
        )
    )
    transitions = sa.or_(
        sa.and_(kind == "add-member", am.is_(True), ag == bg),
        sa.and_(kind == "remove-member", am.is_(False), ag.is_(False)),
        sa.and_(kind == "appoint-manager", am.is_(True), ag.is_(True)),
        sa.and_(kind == "remove-manager", am == bm, ag.is_(False)),
    )
    op.create_table(
        "access_group_relationship_results",
        *_result_columns(),
        sa.Column("principal_id", sa.Uuid(), nullable=False),
        sa.Column("change_kind", sa.String(32), nullable=False),
        *(
            sa.Column(n, sa.Boolean(), nullable=False)
            for n in ("before_member", "before_manager", "member", "manager", "changed")
        ),
        sa.Column("status_code", sa.Integer(), nullable=False),
        _operation_fk("fk_access_group_relationship_operation"),
        sa.CheckConstraint(
            sa.and_(revisions, after - before == sa.case((changed.is_(True), 1), else_=0)),
            name="ck_access_group_relationship_revisions",
        ),
        sa.CheckConstraint(
            sa.and_(
                sa.or_(bg.is_(False), bm.is_(True)),
                sa.or_(ag.is_(False), am.is_(True)),
                changed == sa.or_(bm != am, bg != ag),
                transitions,
                status
                == sa.case(
                    (sa.and_(changed.is_(True), kind.in_(("add-member", "appoint-manager"))), 201),
                    else_=200,
                ),
            ),
            name="ck_access_group_relationship_transition",
        ),
    )
    op.create_table(
        "access_group_deletion_results",
        *_result_columns(),
        _operation_fk("fk_access_group_deletion_operation"),
        sa.CheckConstraint(
            sa.and_(revisions, after - before == 1), name="ck_access_group_deletion_revisions"
        ),
    )


def downgrade() -> None:
    retained = sa.table("deletion_status_bindings", sa.column("authority_family"))
    if op.get_bind().scalar(
        sa.select(sa.func.count())
        .select_from(retained)
        .where(retained.c.authority_family == "access_group_deletion")
    ):
        raise RuntimeError("Retained group deletion status prevents this downgrade.")

    for name in (
        "access_group_creation_results",
        "access_group_relationship_results",
        "access_group_deletion_results",
        "access_group_name_reservations",
    ):
        if op.get_bind().scalar(sa.select(sa.func.count()).select_from(sa.table(name))):
            raise RuntimeError(
                "Retained group identities or administration results prevent this downgrade."
            )
    for name in (
        "access_group_deletion_results",
        "access_group_relationship_results",
        "access_group_creation_results",
    ):
        op.drop_table(name)
    op.drop_constraint("fk_access_group_reserved_name", "access_groups", type_="foreignkey")
    op.drop_table("access_group_name_reservations")
    op.drop_constraint("uq_access_group_name", "access_groups", type_="unique")
    op.drop_constraint("ck_access_group_name", "access_groups", type_="check")
    op.drop_column("access_groups", "resource_name")
    op.drop_constraint("ck_idempotency_lookup_authority", "idempotency_reservations", type_="check")
    op.create_check_constraint(
        "ck_idempotency_lookup_authority",
        "idempotency_reservations",
        _lookup_constraint(groups=False),
    )
