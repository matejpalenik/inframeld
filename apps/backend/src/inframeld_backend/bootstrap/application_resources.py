"""Identify the process resources owned by one application lifespan."""

from dataclasses import dataclass

from ory_kratos_client.api_client import ApiClient

from inframeld_backend.shared.infrastructure.postgres.database import Database


@dataclass(frozen=True, slots=True)
class ApplicationResources:
    """Group the database and optional Kratos client that must be released together."""

    database: Database
    kratos_client: ApiClient | None = None
