"""Keep numeric revisions exact across JSON clients and persisted original results."""

import sqlalchemy as sa
from alembic import op
from migrations.types import MigrationRevisionReference
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0023_safe_numeric_revisions"
down_revision: MigrationRevisionReference = "0022_project_grant_results"
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None

_MAX_REVISION = 9_007_199_254_740_991
_REVISION_COLUMNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("organizations", ("access_revision",)),
    ("projects", ("access_revision", "metadata_revision")),
    ("first_administrator_bootstrap_receipts", ("before_revision", "after_revision")),
    ("human_admission_operation_results", ("before_revision", "access_revision")),
    ("project_action_grant_operation_results", ("before_revision", "access_revision")),
    ("project_creation_operation_results", ("access_revision", "metadata_revision")),
    ("project_membership_operation_results", ("before_revision", "access_revision")),
    ("project_metadata_operation_results", ("metadata_revision",)),
    ("project_metadata_repair_receipts", ("before_revision", "after_revision")),
    ("project_name_reservations", ("binding_revision",)),
    ("deletion_status_observations", ("owner_revision", "unfinished_source_revision")),
    (
        "model_call_accounting",
        ("revision", "reservation_policy_revision", "approved_policy_revision"),
    ),
    (
        "model_call_accounting_evidence",
        (
            "applied_revision",
            "applied_approved_policy_revision",
            "resolution_revision",
            "resolution_approved_policy_revision",
        ),
    ),
    ("project_spending_policy_operation_results", ("revision",)),
    ("project_spending_policies", ("revision",)),
)

_CONSTRAINT_OWNERS = {
    "organizations": "organization",
    "projects": "project",
    "first_administrator_bootstrap_receipts": "bootstrap",
    "human_admission_operation_results": "admission",
    "project_action_grant_operation_results": "project_grant",
    "project_creation_operation_results": "project_creation",
    "project_membership_operation_results": "membership",
    "project_metadata_operation_results": "metadata",
    "project_metadata_repair_receipts": "metadata_repair",
    "project_name_reservations": "project_name",
    "deletion_status_observations": "deletion_status",
    "model_call_accounting": "call_accounting",
    "model_call_accounting_evidence": "call_evidence",
    "project_spending_policy_operation_results": "policy_result",
    "project_spending_policies": "spending_policy",
}


def upgrade() -> None:
    connection = op.get_bind()
    for table_name, names in _REVISION_COLUMNS:
        columns = tuple(sa.column(name, sa.BigInteger()) for name in names)
        table = sa.table(table_name, *columns)
        invalid = sa.or_(*(column > _MAX_REVISION for column in columns))
        if connection.scalar(sa.select(sa.exists().where(invalid).select_from(table))):
            raise RuntimeError("Stored revisions exceed the supported exact integer range.")

    audit_columns = tuple(sa.column(name, JSONB()) for name in ("before_values", "after_values"))
    audit = sa.table("access_audit_events", *audit_columns)
    for column in audit_columns:
        for key in (
            "access_revision",
            "metadata_revision",
            "before_revision",
            "after_revision",
            "call_revision",
            "revision",
        ):
            value = column[key]
            numeric = sa.case(
                (sa.func.jsonb_typeof(value) == "number", sa.cast(value.astext, sa.Numeric())),
                else_=None,
            )
            if connection.scalar(
                sa.select(sa.exists().where(numeric > _MAX_REVISION).select_from(audit))
            ):
                raise RuntimeError(
                    "Stored audit revisions exceed the supported exact integer range."
                )

    for table_name in ("organizations", "projects"):
        op.alter_column(
            table_name,
            "access_revision",
            existing_type=sa.Integer(),
            type_=sa.BigInteger(),
            existing_nullable=False,
        )

    for table_name, names in _REVISION_COLUMNS:
        for name in names:
            op.create_check_constraint(
                f"ck_safe_{_CONSTRAINT_OWNERS[table_name]}_{name}",
                table_name,
                sa.column(name, sa.BigInteger()) <= _MAX_REVISION,
            )


def downgrade() -> None:
    connection = op.get_bind()
    for table_name in ("organizations", "projects"):
        table = sa.table(table_name, sa.column("access_revision", sa.BigInteger()))
        if connection.scalar(
            sa.select(sa.exists().where(table.c.access_revision > 2**31 - 1).select_from(table))
        ):
            raise RuntimeError("Stored Access revisions cannot fit the previous integer columns.")

    for table_name, names in reversed(_REVISION_COLUMNS):
        for name in reversed(names):
            op.drop_constraint(
                f"ck_safe_{_CONSTRAINT_OWNERS[table_name]}_{name}", table_name, type_="check"
            )

    for table_name in ("organizations", "projects"):
        op.alter_column(
            table_name,
            "access_revision",
            existing_type=sa.BigInteger(),
            type_=sa.Integer(),
            existing_nullable=False,
        )
