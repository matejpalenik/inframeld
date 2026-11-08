"""Bind each selected adapter literally and retain safe issuance originals."""

import sqlalchemy as sa
from alembic import op
from migrations.types import MigrationRevisionReference
from sqlalchemy.dialects.postgresql import ARRAY

revision: str = "0028_application_key_issuance"
down_revision: MigrationRevisionReference = "0027_invitations"
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None


def upgrade() -> None:
    op.add_column("application_keys", sa.Column("http_audience", sa.Text(), nullable=True))
    op.add_column("application_keys", sa.Column("mcp_audience", sa.Text(), nullable=True))
    adapter_type = ARRAY(sa.String(8))
    keys = sa.table(
        "application_keys",
        sa.column("audience", sa.Text()),
        sa.column("allowed_adapters", adapter_type),
        sa.column("http_audience", sa.Text()),
        sa.column("mcp_audience", sa.Text()),
    )
    http = keys.c.allowed_adapters.contains(
        sa.cast(sa.literal(["http"], type_=adapter_type), adapter_type)
    )
    mcp = keys.c.allowed_adapters.contains(
        sa.cast(sa.literal(["mcp"], type_=adapter_type), adapter_type)
    )
    op.execute(
        keys.update().values(
            http_audience=sa.case((http, keys.c.audience), else_=None),
            mcp_audience=sa.case((mcp, keys.c.audience), else_=None),
        )
    )
    for adapter, selected in (("http", http), ("mcp", mcp)):
        audience = keys.c[f"{adapter}_audience"]
        op.create_check_constraint(
            f"ck_application_key_{adapter}_binding",
            "application_keys",
            sa.or_(
                sa.and_(
                    selected,
                    audience.is_not(None),
                    sa.func.length(sa.func.trim(audience)) > 0,
                ),
                sa.and_(~selected, audience.is_(None)),
            ),
        )
    op.drop_constraint("ck_application_key_audience", "application_keys", type_="check")
    op.drop_column("application_keys", "audience")

    before = sa.column("before_revision", sa.BigInteger())
    after = sa.column("access_revision", sa.BigInteger())
    created = sa.column("created_at", sa.DateTime(timezone=True))
    expires = sa.column("expires_at", sa.DateTime(timezone=True))
    adapters = sa.column("allowed_adapters", adapter_type)
    op.create_table(
        "application_key_issuance_results",
        sa.Column("operation_id", sa.Text(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("application_principal_id", sa.Uuid(), nullable=False),
        sa.Column("installation_id", sa.Uuid(), nullable=False),
        sa.Column("issuer_principal_id", sa.Uuid(), nullable=False),
        sa.Column("key_id", sa.Uuid(), nullable=False),
        sa.Column("allowed_adapters", adapter_type, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("before_revision", sa.BigInteger(), nullable=False),
        sa.Column("access_revision", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["operation_id", "organization_id", "project_id", "issuer_principal_id"],
            [
                "idempotency_reservations.operation_id",
                "idempotency_reservations.organization_id",
                "idempotency_reservations.project_id",
                "idempotency_reservations.principal_id",
            ],
            name="fk_application_key_issuance_operation",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id", "application_principal_id"],
            [
                "application_accounts.organization_id",
                "application_accounts.project_id",
                "application_accounts.principal_id",
            ],
            name="fk_application_key_issuance_account",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["installation_id"],
            ["installation_identity.installation_id"],
            name="fk_application_key_issuance_installation",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            sa.and_(
                before.between(0, 9007199254740990),
                after.between(1, 9007199254740991),
                after - before == 1,
            ),
            name="ck_application_key_issuance_revision",
        ),
        sa.CheckConstraint(expires > created, name="ck_application_key_issuance_lifetime"),
        sa.CheckConstraint(
            sa.column("revoked_at").is_(None), name="ck_application_key_issuance_original_unrevoked"
        ),
        sa.CheckConstraint(
            adapters.in_(
                tuple(
                    sa.cast(sa.literal(value, type_=adapter_type), adapter_type)
                    for value in (["http"], ["mcp"], ["http", "mcp"], ["mcp", "http"])
                )
            ),
            name="ck_application_key_issuance_adapters",
        ),
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.select(sa.func.count()).select_from(sa.table("application_key_issuance_results"))
    ):
        raise RuntimeError("Retained application-key issuance originals prevent this downgrade.")
    keys = sa.table(
        "application_keys",
        sa.column("http_audience", sa.Text()),
        sa.column("mcp_audience", sa.Text()),
        sa.column("audience", sa.Text()),
    )
    if op.get_bind().scalar(
        sa.select(sa.func.count())
        .select_from(keys)
        .where(
            keys.c.http_audience.is_not(None),
            keys.c.mcp_audience.is_not(None),
            keys.c.http_audience.is_distinct_from(keys.c.mcp_audience),
        )
    ):
        raise RuntimeError("Unequal application-key adapter bindings prevent this downgrade.")

    op.add_column("application_keys", sa.Column("audience", sa.Text(), nullable=True))
    op.execute(
        keys.update().values(audience=sa.func.coalesce(keys.c.http_audience, keys.c.mcp_audience))
    )
    op.alter_column("application_keys", "audience", nullable=False)
    op.create_check_constraint(
        "ck_application_key_audience",
        "application_keys",
        sa.func.length(sa.func.trim(keys.c.audience)) > 0,
    )
    op.drop_constraint("ck_application_key_http_binding", "application_keys", type_="check")
    op.drop_constraint("ck_application_key_mcp_binding", "application_keys", type_="check")
    op.drop_column("application_keys", "http_audience")
    op.drop_column("application_keys", "mcp_audience")
    op.drop_table("application_key_issuance_results")
