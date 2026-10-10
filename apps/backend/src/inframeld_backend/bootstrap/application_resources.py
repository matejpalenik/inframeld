"""Identify the process resources owned by one application lifespan."""

from dataclasses import dataclass

from ory_hydra_client.api_client import ApiClient as HydraApiClient
from ory_kratos_client.api_client import ApiClient as KratosApiClient

from inframeld_backend.shared.infrastructure.resources.database import Database


@dataclass(frozen=True, slots=True)
class ApplicationResources:
    """Group the database and optional Kratos client that must be released together."""

    database: Database
    kratos_client: KratosApiClient | None = None
    kratos_admin_client: KratosApiClient | None = None
    hydra_client: HydraApiClient | None = None
