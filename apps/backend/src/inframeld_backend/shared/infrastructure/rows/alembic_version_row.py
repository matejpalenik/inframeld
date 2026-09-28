from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.shared.infrastructure.rows.migration_metadata_base import (
    MigrationMetadataBase,
)


class AlembicVersionRow(MigrationMetadataBase):
    """Represent the installed revision recorded by Alembic itself."""

    __tablename__ = "alembic_version"
    version_num: Mapped[str] = mapped_column(String(32), primary_key=True)
