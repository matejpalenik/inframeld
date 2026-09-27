"""Start and release application resources around request serving."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from inframeld_backend.bootstrap.application_resources import ApplicationResources


@asynccontextmanager
async def application_lifespan(
    resources: ApplicationResources, _application: FastAPI | None = None
) -> AsyncGenerator[None]:
    """Own database startup and release every resource, including after partial startup."""
    try:
        await resources.database.startup()
        yield
    finally:
        try:
            await resources.database.shutdown()
        finally:
            if resources.kratos_client is not None:
                # The SDK __exit__ is a no-op; release the actual urllib3 pools.
                resources.kratos_client.rest_client.pool_manager.clear()
