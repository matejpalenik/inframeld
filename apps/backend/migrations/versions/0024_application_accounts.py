"""Create empty application identities, retained receipts and safe credential metadata."""

import json

import sqlalchemy as sa
from alembic import op
from migrations.types import MigrationRevisionReference
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

revision: str = "0024_application_accounts"
down_revision: MigrationRevisionReference = "0023_safe_numeric_revisions"
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None
_MAX_REVISION = 9007199254740991
_ACTIONS = ["issue-application-keys", "revoke-application-keys", "delete-application-account"]


def upgrade() -> None:
    kind = sa.column("principal_kind", sa.String())
    principal = sa.column("principal_id", sa.Uuid())
    application = sa.column("application_principal_id", sa.Uuid())
    op.drop_constraint(
        "ck_project_memberships_application_binding", "project_memberships", type_="check"
    )
    # Explicit non-null rejects UNKNOWN, which would otherwise bypass both this
    # check and the application membership's composite foreign key.
    op.create_check_constraint(
        "ck_project_memberships_application_binding",
        "project_memberships",
        sa.or_(
            sa.and_(kind == "human", application.is_(None)),
            sa.and_(kind == "application", application.is_not(None), application == principal),
        ),
    )
    op.add_column("application_accounts", sa.Column("resource_name", sa.Text(), nullable=True))
    name = sa.column("resource_name", sa.Text())
    op.create_check_constraint(
        "ck_application_account_name",
        "application_accounts",
        sa.or_(
            name.is_(None),
            sa.and_(
                sa.func.length(name).between(1, 63), name.op("~")("^[a-z]([a-z0-9-]*[a-z0-9])?$")
            ),
        ),
    )
    op.create_unique_constraint(
        "uq_application_account_name", "application_accounts", ["project_id", "resource_name"]
    )
    op.create_unique_constraint(
        "uq_application_account_scope",
        "application_accounts",
        ["organization_id", "project_id", "principal_id"],
    )
    op.create_table(
        "application_account_name_reservations",
        sa.Column("project_id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.Text(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("application_principal_id", sa.Uuid(), nullable=False),
        sa.Column("retired", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id", "application_principal_id"],
            [
                "application_accounts.organization_id",
                "application_accounts.project_id",
                "application_accounts.principal_id",
            ],
            name="fk_application_name_account",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            sa.and_(
                sa.func.length(sa.column("name")).between(1, 63),
                sa.column("name").op("~")("^[a-z]([a-z0-9-]*[a-z0-9])?$"),
            ),
            name="ck_application_reserved_name",
        ),
    )
    op.create_unique_constraint(
        "uq_application_creation_operation_scope",
        "idempotency_reservations",
        ["operation_id", "organization_id", "project_id", "principal_id"],
    )
    before, after = (
        sa.column("before_revision", sa.BigInteger()),
        sa.column("access_revision", sa.BigInteger()),
    )
    op.create_table(
        "application_account_creation_results",
        sa.Column("operation_id", sa.Text(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("principal_id", sa.Uuid(), nullable=False),
        sa.Column("creator_principal_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("before_revision", sa.BigInteger(), nullable=False),
        sa.Column("access_revision", sa.BigInteger(), nullable=False),
        sa.Column("initial_actions", JSONB(), nullable=False),
        sa.ForeignKeyConstraint(
            ["operation_id", "organization_id", "project_id", "creator_principal_id"],
            [
                "idempotency_reservations.operation_id",
                "idempotency_reservations.organization_id",
                "idempotency_reservations.project_id",
                "idempotency_reservations.principal_id",
            ],
            name="fk_application_creation_operation",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id", "principal_id"],
            [
                "application_accounts.organization_id",
                "application_accounts.project_id",
                "application_accounts.principal_id",
            ],
            name="fk_application_creation_account",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            sa.and_(
                before >= 0,
                before < _MAX_REVISION,
                after > 0,
                after <= _MAX_REVISION,
                after - before == 1,
            ),
            name="ck_application_creation_revisions",
        ),
        sa.CheckConstraint(
            sa.column("initial_actions", JSONB())
            == sa.cast(sa.literal(json.dumps(_ACTIONS)), JSONB()),
            name="ck_application_creation_actions",
        ),
    )
    created, expires, revoked = (
        sa.column("created_at"),
        sa.column("expires_at"),
        sa.column("revoked_at"),
    )
    adapter_type = ARRAY(sa.String(8))
    adapters = sa.column("allowed_adapters", adapter_type)
    op.create_table(
        "application_keys",
        sa.Column("key_id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("application_principal_id", sa.Uuid(), nullable=False),
        sa.Column("installation_id", sa.Uuid(), nullable=False),
        sa.Column("audience", sa.Text(), nullable=False),
        sa.Column("allowed_adapters", adapter_type, nullable=False),
        sa.Column("verifier", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("issued_by_principal_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id", "application_principal_id"],
            [
                "application_accounts.organization_id",
                "application_accounts.project_id",
                "application_accounts.principal_id",
            ],
            name="fk_application_key_account",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["installation_id"],
            ["installation_identity.installation_id"],
            name="fk_application_key_installation",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "issued_by_principal_id"],
            ["principals.organization_id", "principals.id"],
            name="fk_application_key_issuer",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            sa.func.octet_length(sa.column("verifier")) == 32, name="ck_application_key_verifier"
        ),
        sa.CheckConstraint(
            sa.func.length(sa.func.trim(sa.column("audience"))) > 0,
            name="ck_application_key_audience",
        ),
        sa.CheckConstraint(
            adapters.in_(
                tuple(
                    sa.cast(sa.literal(value, type_=adapter_type), adapter_type)
                    for value in (["http"], ["mcp"], ["http", "mcp"], ["mcp", "http"])
                )
            ),
            name="ck_application_key_adapters",
        ),
        sa.CheckConstraint(
            sa.and_(expires > created, sa.or_(revoked.is_(None), revoked >= created)),
            name="ck_application_key_lifecycle",
        ),
    )
    op.create_index(
        "ix_application_keys_account",
        "application_keys",
        ["project_id", "application_principal_id", "key_id"],
    )


def downgrade() -> None:
    for name in (
        "application_account_creation_results",
        "application_account_name_reservations",
        "application_keys",
    ):
        if op.get_bind().scalar(sa.select(sa.func.count()).select_from(sa.table(name))):
            raise RuntimeError(
                "Retained application identities or credentials prevent this downgrade."
            )
    op.drop_table("application_keys")
    op.drop_table("application_account_creation_results")
    op.drop_constraint(
        "uq_application_creation_operation_scope", "idempotency_reservations", type_="unique"
    )
    op.drop_table("application_account_name_reservations")
    op.drop_constraint("uq_application_account_scope", "application_accounts", type_="unique")
    op.drop_constraint("uq_application_account_name", "application_accounts", type_="unique")
    op.drop_constraint("ck_application_account_name", "application_accounts", type_="check")
    op.drop_column("application_accounts", "resource_name")
    kind = sa.column("principal_kind", sa.String())
    principal = sa.column("principal_id", sa.Uuid())
    application = sa.column("application_principal_id", sa.Uuid())
    op.drop_constraint(
        "ck_project_memberships_application_binding", "project_memberships", type_="check"
    )
    op.create_check_constraint(
        "ck_project_memberships_application_binding",
        "project_memberships",
        sa.or_(
            sa.and_(kind == "human", application.is_(None)),
            sa.and_(kind == "application", application == principal),
        ),
    )
