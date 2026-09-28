"""Define typed records used only by database and migration behavior tests."""

from sqlalchemy import Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, MappedAsDataclass, mapped_column


class DatabaseTestBase(MappedAsDataclass, DeclarativeBase, kw_only=True):
    """Keep test-only mappings out of the application schema metadata."""


class DatabaseTestRow(DatabaseTestBase):
    """Store a unique label for transaction visibility and rollback scenarios."""

    __tablename__ = "database_integration"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String, unique=True)


class MissingTestRow(DatabaseTestBase):
    """Name a table deliberately never created so real SQL execution fails."""

    __tablename__ = "intentionally_missing_test_table"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)


class MigrationSentinelRow(DatabaseTestBase):
    """Hold a value that must survive an idempotent migration invocation."""

    __tablename__ = "migration_sentinel"
    value: Mapped[str] = mapped_column(String, primary_key=True)
