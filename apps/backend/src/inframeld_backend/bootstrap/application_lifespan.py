"""Start and release application resources around request serving."""

from collections.abc import AsyncGenerator
from contextlib import ExitStack, asynccontextmanager

from fastapi import FastAPI

from inframeld_backend.bootstrap.application_resources import ApplicationResources


@asynccontextmanager
async def application_lifespan(
    resources: ApplicationResources, _application: FastAPI | None = None
) -> AsyncGenerator[None]:
    """Release every provider pool even when database startup or shutdown fails."""
    with ExitStack() as provider_cleanup:
        for client in (
            resources.kratos_client,
            resources.kratos_admin_client,
            resources.hydra_client,
        ):
            if client is not None:
                # The SDK context-manager exit does not release urllib3 pools.
                provider_cleanup.callback(client.rest_client.pool_manager.clear)

        try:
            await resources.database.startup()
            yield
        finally:
            await resources.database.shutdown()
