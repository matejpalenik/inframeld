"""Preserve human credential generations independently of cleanup record retention."""

import sqlalchemy as sa
from alembic import op
from migrations.types import MigrationRevisionReference

revision: str = "0005_human_credential_versions"
down_revision: MigrationRevisionReference = "0004_identity_recovery"
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None


def upgrade() -> None:
    versions = op.create_table(
        "human_credential_versions",
        sa.Column("installation_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("authority", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint(
            "installation_id", "authority", "subject", name="pk_human_credential_versions"
        ),
        sa.ForeignKeyConstraint(
            ["installation_id"],
            ["installation_identity.installation_id"],
            name="fk_human_credential_versions_installation",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            sa.column("version", sa.BigInteger()) > 0, name="ck_human_credential_version_positive"
        ),
    )
    installation = sa.table(
        "installation_identity", sa.column("installation_id", sa.Uuid(as_uuid=True))
    )
    links = sa.table(
        "human_identity_links", sa.column("authority", sa.Text()), sa.column("subject", sa.Text())
    )
    recoveries = sa.table(
        "identity_recovery_admissions",
        sa.column("installation_id", sa.Uuid(as_uuid=True)),
        sa.column("authority", sa.Text()),
        sa.column("subject", sa.Text()),
    )
    identities = (
        sa.select(installation.c.installation_id, links.c.authority, links.c.subject)
        .select_from(installation.join(links, sa.true()))
        .union(
            sa.select(recoveries.c.installation_id, recoveries.c.authority, recoveries.c.subject)
        )
        .subquery()
    )
    op.get_bind().execute(
        versions.insert().from_select(
            ["installation_id", "authority", "subject", "version"],
            sa.select(
                identities.c.installation_id,
                identities.c.authority,
                identities.c.subject,
                sa.literal(1),
            ),
        )
    )


def downgrade() -> None:
    raise RuntimeError("Downgrading human credential versions is unsupported.")
