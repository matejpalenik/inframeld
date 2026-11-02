"""Retain immutable creation outcomes without retargeting Organization reservations."""

import json

import sqlalchemy as sa
from alembic import op
from migrations.types import MigrationRevisionReference
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0017_project_creation"
down_revision: MigrationRevisionReference = "0016_first_administrator"
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None

_INITIAL_ACTIONS = [
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
    "edit-project-metadata",
]


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_project_creation_operation_scope",
        "idempotency_reservations",
        ["operation_id", "organization_id", "principal_id"],
    )
    op.create_table(
        "project_creation_operation_results",
        sa.Column("operation_id", sa.Text(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("creator_principal_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("access_revision", sa.BigInteger(), nullable=False),
        sa.Column("metadata_revision", sa.BigInteger(), nullable=False),
        sa.Column("initial_actions", JSONB(), nullable=False),
        sa.ForeignKeyConstraint(
            ["operation_id", "organization_id", "creator_principal_id"],
            [
                "idempotency_reservations.operation_id",
                "idempotency_reservations.organization_id",
                "idempotency_reservations.principal_id",
            ],
            name="fk_project_creation_operation",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            sa.and_(sa.column("access_revision") == 1, sa.column("metadata_revision") == 0),
            name="ck_project_creation_revisions",
        ),
        sa.CheckConstraint(
            sa.column("initial_actions", JSONB())
            == sa.cast(sa.literal(json.dumps(_INITIAL_ACTIONS)), JSONB()),
            name="ck_project_creation_initial_actions",
        ),
    )


def downgrade() -> None:
    results = sa.table("project_creation_operation_results", sa.column("operation_id"))
    if op.get_bind().scalar(sa.select(sa.func.count()).select_from(results)):
        raise RuntimeError("Retained Project creation outcomes prevent this downgrade.")
    op.drop_table("project_creation_operation_results")
    op.drop_constraint(
        "uq_project_creation_operation_scope", "idempotency_reservations", type_="unique"
    )
