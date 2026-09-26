"""Provision isolated test databases and typed SQLAlchemy sessions."""

from collections.abc import Generator
from contextlib import contextmanager
from uuid import uuid4

import psycopg
from psycopg import sql
from sqlalchemy import URL, Connection, create_engine
from sqlalchemy.orm import Session

from inframeld_backend.access.infrastructure.rows.access_persistence_base import (
    AccessPersistenceBase,
)
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings


def database_url(settings: DatabaseSettings) -> URL:
    """Build a driver URL without embedding credentials into SQL or diagnostics."""
    return URL.create(
        "postgresql+psycopg",
        host=settings.host,
        port=settings.port,
        database=settings.name,
        username=settings.user,
        password=settings.password.get_secret_value(),
    )


@contextmanager
def temporary_database(settings: DatabaseSettings) -> Generator[DatabaseSettings]:
    """Create and remove a test-only database using the approved administration exception.

    CREATE/DROP DATABASE have no ORM equivalent. SQL composition is confined to
    this helper and identifiers are quoted by psycopg; record access uses ORM.
    """
    name = f"inframeld_test_{uuid4().hex}"
    with psycopg.connect(
        host=settings.host,
        port=settings.port,
        dbname="postgres",
        user=settings.user,
        password=settings.password.get_secret_value(),
        autocommit=True,
    ) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            yield settings.model_copy(update={"name": name})
        finally:
            connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )


@contextmanager
def database_connection(
    settings: DatabaseSettings, *, autocommit: bool = False
) -> Generator[Connection]:
    """Own a synchronous SQLAlchemy connection for schema and migration scenarios."""
    engine = create_engine(database_url(settings), hide_parameters=True)
    try:
        with engine.connect() as connection:
            if autocommit:
                connection = connection.execution_options(isolation_level="AUTOCOMMIT")
            yield connection
    finally:
        engine.dispose()


@contextmanager
def database_session(settings: DatabaseSettings) -> Generator[Session]:
    """Own a synchronous ORM session and its engine for one constraint scenario."""
    engine = create_engine(database_url(settings), hide_parameters=True)
    try:
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()


def insert_row(session: Session, row: AccessPersistenceBase) -> None:
    """Flush one typed fixture row inside a savepoint to isolate expected violations."""
    with session.begin_nested():
        session.add(row)
        session.flush()
