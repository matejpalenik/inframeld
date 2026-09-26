"""Provide typed ORM constructors; Alembic owns the actual database schema."""

from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass


class AccessPersistenceBase(MappedAsDataclass, DeclarativeBase, kw_only=True, eq=False):
    """Base for Access database row mappings."""
