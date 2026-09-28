from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass


class SharedPersistenceBase(MappedAsDataclass, DeclarativeBase, kw_only=True, eq=False):
    """Provide typed constructors for shared supporting records."""
