"""Read Alembic's existing version table without taking ownership of its schema."""

from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, Mapped, MappedAsDataclass, mapped_column


class MigrationMetadataBase(MappedAsDataclass, DeclarativeBase, kw_only=True):
    """Isolate migration metadata mappings from application-owned tables."""


class AlembicVersionRow(MigrationMetadataBase):
    """Represent the installed revision recorded by Alembic itself."""

    __tablename__ = "alembic_version"
    version_num: Mapped[str] = mapped_column(String(32), primary_key=True)
