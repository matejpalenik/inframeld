"""Retain scoped spending obligations and evidence independently of expiring replay data."""

import sqlalchemy as sa
from alembic import op
from migrations.types import MigrationRevisionReference
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.elements import ColumnElement

revision: str = "0018_spending_accounting"
down_revision: MigrationRevisionReference = "0017_project_creation"
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None


def _amount(name: str, *, quantized: bool = True) -> ColumnElement[bool]:
    """Reject invalid amounts without a Numeric scale silently rounding the input.

    Raw observed charges can be smaller than the accounting quantum. Rates and
    usage retain their original decimal strings in the captured JSON records.
    """
    amount = sa.column(name, sa.Numeric())
    finite = sa.and_(
        amount >= 0,
        amount.not_in(
            [
                sa.cast(sa.literal(value, type_=sa.String()), sa.Numeric())
                for value in ("NaN", "Infinity", "-Infinity")
            ]
        ),
    )
    valid = (
        sa.case((finite, amount == sa.func.trunc(amount, 12)), else_=False) if quantized else finite
    )
    return sa.or_(amount.is_(None), valid)


def _financial_state(prefix: str = "") -> ColumnElement[bool]:
    """Keep terminal zero holds and unknown active obligations representable."""
    state = sa.column(f"{prefix}state", sa.String())
    hold = sa.column(f"{prefix}hold_amount", sa.Numeric())
    settled = sa.column(f"{prefix}settled_amount", sa.Numeric())
    approved = sa.column(f"{prefix}approved_policy_revision", sa.BigInteger())
    return sa.and_(
        sa.or_(
            sa.and_(
                state.in_(["reserved", "accounting_approved", "unresolved"]),
                settled.is_(None),
            ),
            sa.and_(state == "settled", hold.is_not(None), hold == 0, settled.is_not(None)),
            sa.and_(
                state == "released",
                hold.is_not(None),
                hold == 0,
                settled.is_not(None),
                settled == 0,
            ),
        ),
        sa.or_(state != "reserved", approved.is_(None)),
        sa.or_(state != "accounting_approved", approved.is_not(None)),
        sa.or_(approved.is_(None), approved >= 0),
    )


def _receipt(prefix: str) -> ColumnElement[bool]:
    """An original receipt is either absent or a complete financial outcome."""
    state = sa.column(f"{prefix}state", sa.String())
    hold = sa.column(f"{prefix}hold_amount", sa.Numeric())
    settled = sa.column(f"{prefix}settled_amount", sa.Numeric())
    receipt_revision = sa.column(f"{prefix}revision", sa.BigInteger())
    approved = sa.column(f"{prefix}approved_policy_revision", sa.BigInteger())
    return sa.or_(
        sa.and_(
            state.is_(None),
            hold.is_(None),
            settled.is_(None),
            receipt_revision.is_(None),
            approved.is_(None),
        ),
        sa.and_(
            state.is_not(None),
            receipt_revision.is_not(None),
            receipt_revision >= 1,
            _financial_state(prefix),
        ),
    )


def upgrade() -> None:
    op.create_table(
        "project_spending_policies",
        sa.Column("project_id", sa.Uuid(as_uuid=True), nullable=False, primary_key=True),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("monthly_limit", sa.Numeric(), nullable=True),
        sa.UniqueConstraint("organization_id", "project_id", name="uq_spending_policy_scope"),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id"],
            ["projects.organization_id", "projects.id"],
            name="fk_spending_policy_project",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(sa.column("revision") >= 0, name="ck_spending_policy_revision"),
        sa.CheckConstraint(_amount("monthly_limit"), name="ck_spending_policy_amount"),
    )
    op.create_table(
        "spending_operations",
        sa.Column("operation_id", sa.Text(), nullable=False, primary_key=True),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("job_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("installation_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("principal_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("principal_kind", sa.String(32), nullable=False),
        sa.Column("action_id", sa.String(100), nullable=False),
        sa.Column("operation_limit", sa.Numeric(), nullable=True),
        sa.Column("human_authority", sa.Text(), nullable=True),
        sa.Column("human_subject", sa.Text(), nullable=True),
        sa.Column("human_version", sa.BigInteger(), nullable=True),
        sa.UniqueConstraint(
            "organization_id", "project_id", "operation_id", name="uq_spending_operation_scope"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id"],
            ["project_spending_policies.organization_id", "project_spending_policies.project_id"],
            name="fk_spending_operation_policy",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "principal_id", "principal_kind"],
            ["principals.organization_id", "principals.id", "principals.kind"],
            name="fk_spending_operation_principal",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(_amount("operation_limit"), name="ck_spending_operation_amount"),
        sa.CheckConstraint(
            sa.and_(
                sa.func.length(sa.func.btrim(sa.column("operation_id"))) > 0,
                sa.func.length(sa.func.btrim(sa.column("action_id"))) > 0,
            ),
            name="ck_spending_operation_identity",
        ),
        sa.CheckConstraint(
            sa.or_(
                sa.and_(
                    sa.column("principal_kind") == "human",
                    sa.column("human_authority").is_not(None),
                    sa.func.length(sa.func.btrim(sa.column("human_authority"))) > 0,
                    sa.column("human_subject").is_not(None),
                    sa.func.length(sa.func.btrim(sa.column("human_subject"))) > 0,
                    sa.column("human_version").is_not(None),
                    sa.column("human_version") >= 1,
                ),
                sa.and_(
                    sa.column("principal_kind") == "application",
                    sa.column("human_authority").is_(None),
                    sa.column("human_subject").is_(None),
                    sa.column("human_version").is_(None),
                ),
            ),
            name="ck_spending_operation_authority",
        ),
    )
    # Job and original operation IDs are attribution, not replay/payload lifetime
    # dependencies. Expiring that metadata must not erase or release an obligation.
    op.create_table(
        "model_call_accounting",
        sa.Column("call_id", sa.Uuid(as_uuid=True), nullable=False, primary_key=True),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("operation_id", sa.Text(), nullable=False),
        sa.Column("meaning_fingerprint", sa.LargeBinary(), nullable=False),
        sa.Column("period_year", sa.BigInteger(), nullable=False),
        sa.Column("period_month", sa.BigInteger(), nullable=False),
        sa.Column("basis", postgresql.JSONB(none_as_null=True), nullable=True),
        sa.Column("reserved_amount", sa.Numeric(), nullable=True),
        sa.Column("hold_amount", sa.Numeric(), nullable=True),
        sa.Column("settled_amount", sa.Numeric(), nullable=True),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("reservation_policy_revision", sa.BigInteger(), nullable=False),
        sa.Column("approved_policy_revision", sa.BigInteger(), nullable=True),
        sa.UniqueConstraint(
            "organization_id", "project_id", "call_id", name="uq_spending_call_scope"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id", "operation_id"],
            [
                "spending_operations.organization_id",
                "spending_operations.project_id",
                "spending_operations.operation_id",
            ],
            name="fk_spending_call_operation",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            sa.and_(
                sa.column("period_year").between(1, 9999),
                sa.column("period_month").between(1, 12),
            ),
            name="ck_spending_call_period",
        ),
        sa.CheckConstraint(
            sa.func.octet_length(sa.column("meaning_fingerprint")) == 32,
            name="ck_spending_call_fingerprint",
        ),
        sa.CheckConstraint(
            sa.or_(
                sa.column("basis").is_(None),
                sa.func.jsonb_typeof(sa.column("basis")) == "object",
            ),
            name="ck_spending_call_basis",
        ),
        sa.CheckConstraint(
            sa.and_(_amount("reserved_amount"), _amount("hold_amount"), _amount("settled_amount")),
            name="ck_spending_call_amounts",
        ),
        sa.CheckConstraint(
            sa.and_(
                sa.column("revision") >= 0,
                sa.column("reservation_policy_revision") >= 0,
                sa.or_(
                    sa.column("approved_policy_revision").is_(None),
                    sa.column("approved_policy_revision")
                    >= sa.column("reservation_policy_revision"),
                ),
            ),
            name="ck_spending_call_revisions",
        ),
        sa.CheckConstraint(_financial_state(), name="ck_spending_call_state"),
        sa.CheckConstraint(
            sa.or_(
                sa.and_(
                    sa.column("state").in_(["reserved", "accounting_approved"]),
                    sa.column("hold_amount").is_not_distinct_from(sa.column("reserved_amount")),
                ),
                sa.and_(
                    sa.column("state") == "unresolved",
                    sa.or_(
                        sa.column("hold_amount").is_(None),
                        sa.column("hold_amount").is_not_distinct_from(sa.column("reserved_amount")),
                    ),
                ),
                sa.column("state").in_(["settled", "released"]),
            ),
            name="ck_spending_call_hold",
        ),
    )
    op.create_table(
        "model_call_accounting_evidence",
        sa.Column("call_id", sa.Uuid(as_uuid=True), nullable=False, primary_key=True),
        sa.Column("evidence_id", sa.Uuid(as_uuid=True), nullable=False, primary_key=True),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_reference", sa.Text(), nullable=False),
        sa.Column("usage", postgresql.JSONB(none_as_null=True), nullable=True),
        sa.Column("charge", sa.Numeric(), nullable=True),
        sa.Column("was_pending", sa.Boolean(), nullable=False),
        sa.Column("applied_state", sa.String(32), nullable=True),
        sa.Column("applied_hold_amount", sa.Numeric(), nullable=True),
        sa.Column("applied_settled_amount", sa.Numeric(), nullable=True),
        sa.Column("applied_revision", sa.BigInteger(), nullable=True),
        sa.Column("applied_approved_policy_revision", sa.BigInteger(), nullable=True),
        sa.Column("resolved_by_evidence_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("resolution_state", sa.String(32), nullable=True),
        sa.Column("resolution_hold_amount", sa.Numeric(), nullable=True),
        sa.Column("resolution_settled_amount", sa.Numeric(), nullable=True),
        sa.Column("resolution_revision", sa.BigInteger(), nullable=True),
        sa.Column("resolution_approved_policy_revision", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id", "call_id"],
            [
                "model_call_accounting.organization_id",
                "model_call_accounting.project_id",
                "model_call_accounting.call_id",
            ],
            name="fk_spending_evidence_call",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["call_id", "resolved_by_evidence_id"],
            [
                "model_call_accounting_evidence.call_id",
                "model_call_accounting_evidence.evidence_id",
            ],
            name="fk_spending_resolution_same_call",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            sa.func.length(sa.func.btrim(sa.column("source_reference"))) > 0,
            name="ck_spending_evidence_source",
        ),
        sa.CheckConstraint(
            sa.or_(
                sa.and_(
                    sa.column("kind") == "usage",
                    sa.column("usage").is_not(None),
                    sa.case(
                        (
                            sa.func.jsonb_typeof(sa.column("usage")) == "array",
                            sa.func.jsonb_array_length(sa.column("usage")) > 0,
                        ),
                        else_=False,
                    ),
                    sa.column("charge").is_(None),
                ),
                sa.and_(
                    sa.column("kind") == "charge",
                    sa.column("usage").is_(None),
                    sa.column("charge").is_not(None),
                ),
                sa.and_(
                    sa.column("kind").in_(["not_sent", "not_billed", "uncertain"]),
                    sa.column("usage").is_(None),
                    sa.column("charge").is_(None),
                ),
            ),
            name="ck_spending_evidence_payload",
        ),
        sa.CheckConstraint(_amount("charge", quantized=False), name="ck_spending_evidence_charge"),
        sa.CheckConstraint(
            sa.and_(
                _amount("applied_hold_amount"),
                _amount("applied_settled_amount"),
                _amount("resolution_hold_amount"),
                _amount("resolution_settled_amount"),
            ),
            name="ck_spending_evidence_receipt_amounts",
        ),
        sa.CheckConstraint(_receipt("applied_"), name="ck_spending_evidence_applied_receipt"),
        sa.CheckConstraint(_receipt("resolution_"), name="ck_spending_evidence_resolution_receipt"),
        sa.CheckConstraint(
            sa.or_(sa.column("was_pending"), sa.column("applied_state").is_not(None)),
            name="ck_spending_evidence_origin",
        ),
        sa.CheckConstraint(
            sa.or_(
                sa.and_(
                    sa.column("resolved_by_evidence_id").is_(None),
                    sa.column("resolution_state").is_(None),
                ),
                sa.and_(
                    sa.column("resolved_by_evidence_id").is_not(None),
                    sa.column("was_pending"),
                    sa.column("resolution_state").is_not(None),
                ),
            ),
            name="ck_spending_evidence_resolution",
        ),
    )
    # Only the small policy replay receipt follows metadata expiry. The policy,
    # calls, original evidence and financial receipts have independent lifetimes.
    op.create_unique_constraint(
        "uq_spending_policy_operation_scope",
        "idempotency_reservations",
        ["operation_id", "organization_id", "project_id", "principal_id"],
    )
    op.create_table(
        "project_spending_policy_operation_results",
        sa.Column("operation_id", sa.Text(), nullable=False, primary_key=True),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("actor_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("monthly_limit", sa.Numeric(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("changed", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["operation_id", "organization_id", "project_id", "actor_id"],
            [
                "idempotency_reservations.operation_id",
                "idempotency_reservations.organization_id",
                "idempotency_reservations.project_id",
                "idempotency_reservations.principal_id",
            ],
            name="fk_spending_policy_result_operation",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id"],
            ["project_spending_policies.organization_id", "project_spending_policies.project_id"],
            name="fk_spending_policy_result_policy",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(_amount("monthly_limit"), name="ck_spending_policy_result_amount"),
        sa.CheckConstraint(
            sa.and_(
                sa.column("revision") >= 0,
                sa.or_(sa.not_(sa.column("changed")), sa.column("revision") > 0),
            ),
            name="ck_spending_policy_result_revision",
        ),
    )


def downgrade() -> None:
    retained_tables = (
        "project_spending_policy_operation_results",
        "model_call_accounting_evidence",
        "model_call_accounting",
        "spending_operations",
        "project_spending_policies",
    )
    connection = op.get_bind()
    for table_name in retained_tables:
        table = sa.table(table_name)
        if connection.scalar(sa.select(sa.func.count()).select_from(table)):
            raise RuntimeError(
                "Retained spending policy, obligations or evidence prevent this downgrade."
            )
    for table_name in retained_tables:
        op.drop_table(table_name)
    op.drop_constraint(
        "uq_spending_policy_operation_scope", "idempotency_reservations", type_="unique"
    )
