"""Retain digest-only invitation intent independently of ordinary issuance history."""

from datetime import timedelta

import sqlalchemy as sa
from alembic import op
from migrations.types import MigrationRevisionReference
from sqlalchemy.dialects import postgresql

revision: str = "0027_invitations"
down_revision: MigrationRevisionReference = "0026_access_action_grant_results"
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None


def upgrade() -> None:
    issued = sa.column("issued_at", sa.DateTime(timezone=True))
    expires = sa.column("expires_at", sa.DateTime(timezone=True))
    consumed = sa.column("consumed_at", sa.DateTime(timezone=True))
    recipient = sa.column("consumed_by_principal_id", sa.Uuid())
    assignments = sa.column("assignments", postgresql.JSONB())
    op.create_table(
        "invitations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("issuer_principal_id", sa.Uuid(), nullable=False),
        sa.Column("token_digest", sa.LargeBinary(), nullable=False),
        sa.Column("assignments", postgresql.JSONB(), nullable=False),
        sa.Column("issued_operation_id", sa.Text(), nullable=False),
        sa.Column("issued_access_revision", sa.BigInteger(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_by_principal_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id", "issuer_principal_id"],
            ["principals.organization_id", "principals.id"],
            name="fk_invitations_scoped_issuer",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "consumed_by_principal_id"],
            ["principals.organization_id", "principals.id"],
            name="fk_invitations_scoped_recipient",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_invitations_scoped_id"),
        # An ordinary operation may expire while its invitation is still valid.
        sa.UniqueConstraint("issued_operation_id", name="uq_invitations_issued_operation"),
        sa.UniqueConstraint("token_digest", name="uq_invitations_digest"),
        sa.CheckConstraint(
            sa.func.octet_length(sa.column("token_digest", sa.LargeBinary())) == 32,
            name="ck_invitations_digest",
        ),
        sa.CheckConstraint(
            sa.case(
                (
                    sa.func.jsonb_typeof(assignments) == "array",
                    sa.func.jsonb_array_length(assignments).between(1, 100),
                ),
                else_=False,
            ),
            name="ck_invitations_assignments",
        ),
        sa.CheckConstraint(
            sa.and_(
                expires > issued,
                expires <= issued + sa.literal(timedelta(days=30), type_=sa.Interval()),
            ),
            name="ck_invitations_lifetime",
        ),
        sa.CheckConstraint(
            sa.column("issued_access_revision", sa.BigInteger()).between(1, 9007199254740991),
            name="ck_invitations_revision",
        ),
        sa.CheckConstraint(
            sa.or_(
                sa.and_(consumed.is_(None), recipient.is_(None)),
                sa.and_(consumed.is_not(None), recipient.is_not(None), consumed >= issued),
            ),
            name="ck_invitations_consumption",
        ),
        sa.CheckConstraint(
            sa.column("revoked_at", sa.DateTime(timezone=True)) >= issued,
            name="ck_invitations_revocation_time",
        ),
    )

    before_revision = sa.column("before_revision", sa.BigInteger())
    access_revision = sa.column("access_revision", sa.BigInteger())
    changed = sa.column("changed", sa.Boolean())
    op.create_table(
        "invitation_revocation_results",
        sa.Column("operation_id", sa.Text(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("actor_principal_id", sa.Uuid(), nullable=False),
        sa.Column("invitation_id", sa.Uuid(), nullable=False),
        sa.Column("before_revision", sa.BigInteger(), nullable=False),
        sa.Column("access_revision", sa.BigInteger(), nullable=False),
        sa.Column("changed", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["operation_id"],
            ["idempotency_reservations.operation_id"],
            name="fk_invitation_revocations_operation",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "actor_principal_id"],
            ["principals.organization_id", "principals.id"],
            name="fk_invitation_revocations_scoped_actor",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "invitation_id"],
            ["invitations.organization_id", "invitations.id"],
            name="fk_invitation_revocations_scoped_invitation",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            sa.and_(
                before_revision.between(1, 9007199254740991),
                access_revision.between(1, 9007199254740991),
                access_revision == before_revision + sa.case((changed, 1), else_=0),
            ),
            name="ck_invitation_revocations_revision",
        ),
    )

    state = sa.column("state", sa.Text())
    principal = sa.column("principal_id", sa.Uuid())
    completed = sa.column("completed_at", sa.DateTime(timezone=True))
    expiry = sa.column("expires_at", sa.DateTime(timezone=True))
    org_revision = sa.column("organization_access_revision", sa.BigInteger())
    project_revisions = sa.column("project_access_revisions", postgresql.JSONB())
    op.create_table(
        "invitation_activation_operations",
        sa.Column("operation_id", sa.Text(), primary_key=True),
        sa.Column("installation_id", sa.Uuid(), nullable=False),
        sa.Column("authority", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("invitation_id", sa.Uuid(), nullable=False),
        sa.Column("issuer_principal_id", sa.Uuid(), nullable=False),
        sa.Column("method", sa.String(16), nullable=False),
        sa.Column("requested_route", sa.Text(), nullable=False),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column("request_fingerprint", sa.LargeBinary(), nullable=False),
        sa.Column("principal_id", sa.Uuid(), nullable=True),
        sa.Column("state", sa.Text(), nullable=False, server_default="in_progress"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.clock_timestamp(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("organization_access_revision", sa.BigInteger(), nullable=True),
        sa.Column("project_access_revisions", postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(
            ["installation_id"],
            ["installation_identity.installation_id"],
            name="fk_invitation_activations_installation",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "invitation_id"],
            ["invitations.organization_id", "invitations.id"],
            name="fk_invitation_activations_invitation",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "issuer_principal_id"],
            ["principals.organization_id", "principals.id"],
            name="fk_invitation_activations_issuer",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "principal_id"],
            ["principals.organization_id", "principals.id"],
            name="fk_invitation_activations_recipient",
            ondelete="RESTRICT",
        ),
        # invitation_id is fingerprint-bound and never splits the same key namespace.
        sa.UniqueConstraint(
            "installation_id",
            "authority",
            "subject",
            "organization_id",
            "method",
            "requested_route",
            "request_key",
            name="uq_invitation_activation_namespace",
        ),
        sa.CheckConstraint(
            sa.and_(
                sa.column("method", sa.Text()) == "POST",
                sa.column("requested_route", sa.Text()) == "/v1/invitations/activate",
            ),
            name="ck_invitation_activation_route",
        ),
        sa.CheckConstraint(
            sa.func.octet_length(sa.column("request_fingerprint", sa.LargeBinary())) == 32,
            name="ck_invitation_activation_fingerprint",
        ),
        sa.CheckConstraint(
            sa.and_(
                sa.func.length(sa.column("authority", sa.Text())) > 0,
                sa.func.length(sa.column("subject", sa.Text())) > 0,
                sa.func.length(sa.column("request_key", sa.Text())) > 0,
            ),
            name="ck_invitation_activation_identity",
        ),
        sa.CheckConstraint(
            sa.or_(
                sa.and_(
                    state == "in_progress",
                    completed.is_(None),
                    expiry.is_(None),
                    org_revision.is_(None),
                    project_revisions.is_(None),
                ),
                sa.and_(
                    state == "replayable",
                    principal.is_not(None),
                    completed.is_not(None),
                    expiry.is_not(None),
                    org_revision.is_not(None),
                    project_revisions.is_not(None),
                    expiry > completed,
                    org_revision.between(1, 9007199254740991),
                    sa.case(
                        (
                            sa.func.jsonb_typeof(project_revisions) == "array",
                            sa.func.jsonb_array_length(project_revisions).between(0, 100),
                        ),
                        else_=False,
                    ),
                ),
            ),
            name="ck_invitation_activation_outcome",
        ),
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.select(sa.func.count()).select_from(sa.table("invitation_activation_operations"))
    ):
        raise RuntimeError("Retained activation operations prevent this downgrade.")
    if op.get_bind().scalar(sa.select(sa.func.count()).select_from(sa.table("invitations"))):
        raise RuntimeError("Retained invitations prevent this downgrade.")
    if op.get_bind().scalar(
        sa.select(sa.func.count()).select_from(sa.table("invitation_revocation_results"))
    ):
        raise RuntimeError("Retained invitation outcomes prevent this downgrade.")
    op.drop_table("invitation_activation_operations")
    op.drop_table("invitation_revocation_results")
    op.drop_table("invitations")
