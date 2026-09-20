from migrations.types import MigrationRevisionReference

revision: str = "0001_initial"
down_revision: MigrationRevisionReference = None
branch_labels: MigrationRevisionReference = None
depends_on: MigrationRevisionReference = None


def upgrade() -> None:
    """Establish the initial schema revision"""
    pass


def downgrade() -> None:
    """Remove the initial schema revision"""
    pass
