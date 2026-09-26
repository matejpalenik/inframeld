from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass


class MigrationMetadataBase(MappedAsDataclass, DeclarativeBase, kw_only=True):
    """Isolate migration metadata mappings from application-owned tables."""
