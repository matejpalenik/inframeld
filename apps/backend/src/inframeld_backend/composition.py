from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI, Request
from ory_kratos_client.api.frontend_api import FrontendApi
from ory_kratos_client.api_client import ApiClient
from ory_kratos_client.configuration import Configuration

from inframeld_backend.access.application.access_authorizer import AccessContext
from inframeld_backend.access.application.human_session import HumanSessionResolver
from inframeld_backend.access.http.current_session import create_session_router
from inframeld_backend.access.http.human_session_authentication import HumanSessionAuthentication
from inframeld_backend.access.infrastructure.kratos_browser_session_verifier import (
    KratosBrowserSessionVerifier,
)
from inframeld_backend.access.infrastructure.postgres_human_identity_link_reader import (
    PostgresHumanIdentityLinkReader,
)
from inframeld_backend.shared.application.errors import DependencyUnavailableError
from inframeld_backend.shared.http.error_handlers import register_error_handlers
from inframeld_backend.shared.http.health import router as health_router
from inframeld_backend.shared.http.problem_openapi import configure_problem_openapi
from inframeld_backend.shared.http.request_context import RequestContextMiddleware
from inframeld_backend.shared.infrastructure.database import Database
from inframeld_backend.shared.infrastructure.logging import configure_logging
from inframeld_backend.shared.infrastructure.settings import Settings, get_settings

API_TITLE = "Inframeld API"
API_VERSION = "0.1.0"


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None]:
    database = cast(Database, application.state.database)

    await database.startup()

    try:
        yield
    finally:
        await database.shutdown()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Construct the API with all concrete dependencies wired explicitly."""

    resolved_settings: Settings = settings if settings is not None else get_settings()

    configure_logging(level=resolved_settings.log_level, log_format=resolved_settings.log_format)

    database = Database(resolved_settings.database)

    kratos_verifier: KratosBrowserSessionVerifier | None = None
    if resolved_settings.kratos is not None:
        kratos_client = ApiClient(
            Configuration(host=str(resolved_settings.kratos.public_url).rstrip("/"))
        )
        kratos_verifier = KratosBrowserSessionVerifier(
            FrontendApi(kratos_client), resolved_settings.kratos.authority
        )

    async def authenticate_human(request: Request) -> AccessContext:
        if kratos_verifier is None:
            raise DependencyUnavailableError()

        async with database.session() as session:
            authentication = HumanSessionAuthentication(
                kratos_verifier.verify,
                HumanSessionResolver(PostgresHumanIdentityLinkReader(session)),
            )
            return await authentication(request)

    application = FastAPI(
        debug=False,
        title=API_TITLE,
        version=API_VERSION,
        description="Governed retrieval and release workflows.",
        openapi_url="/v1/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    register_error_handlers(application)
    configure_problem_openapi(application)

    application.include_router(health_router)
    application.include_router(create_session_router(authenticate_human))
    application.add_middleware(RequestContextMiddleware)

    application.state.database = database

    return application
