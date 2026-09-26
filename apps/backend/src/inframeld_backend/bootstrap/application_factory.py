"""Construct the HTTP application and connect its concrete resources and services."""

from functools import partial

from fastapi import FastAPI

from inframeld_backend.access.http.authentication.current_session_routes import (
    create_session_router,
)
from inframeld_backend.access.http.authentication.human_session_dependency import (
    HumanSessionDependency,
)
from inframeld_backend.bootstrap.access_composition import create_access_components
from inframeld_backend.bootstrap.application_lifespan import application_lifespan
from inframeld_backend.bootstrap.application_resources import ApplicationResources
from inframeld_backend.bootstrap.application_settings import ApplicationSettings, get_settings
from inframeld_backend.shared.http.errors.error_handlers import register_error_handlers
from inframeld_backend.shared.http.errors.problem_openapi import configure_problem_openapi
from inframeld_backend.shared.http.health_routes import router as health_router
from inframeld_backend.shared.http.request_context_middleware import RequestContextMiddleware
from inframeld_backend.shared.infrastructure.observability.logging_configuration import (
    configure_logging,
)
from inframeld_backend.shared.infrastructure.postgres.database import Database

API_TITLE = "Inframeld API"
API_VERSION = "0.1.0"


def create_app(settings: ApplicationSettings | None = None) -> FastAPI:
    """Construct resources, wire application services, and register HTTP behavior.

    Construction performs no network I/O. The lifespan starts PostgreSQL checks
    and releases both database and provider resources, including startup failure.
    """
    resolved_settings = settings if settings is not None else get_settings()
    configure_logging(level=resolved_settings.log_level, log_format=resolved_settings.log_format)
    database = Database(resolved_settings.database)
    access = create_access_components(resolved_settings.kratos, database)
    resources = ApplicationResources(database, access.kratos_client)
    application = FastAPI(
        debug=False,
        title=API_TITLE,
        version=API_VERSION,
        description="Governed retrieval and release workflows.",
        openapi_url="/v1/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=partial(application_lifespan, resources),
    )
    register_error_handlers(application)
    configure_problem_openapi(application)
    application.include_router(health_router)
    application.include_router(create_session_router(HumanSessionDependency(access.authenticator)))
    application.add_middleware(RequestContextMiddleware)
    return application
