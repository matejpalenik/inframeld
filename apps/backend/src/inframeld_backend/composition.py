from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from inframeld_backend.shared.http.health import router as health_router
from inframeld_backend.shared.infrastructure.logging import configure_logging
from inframeld_backend.shared.infrastructure.settings import Settings, get_settings

API_TITLE = "Inframeld API"
API_VERSION = "0.1.0"
OPENAPI_VERSION = "3.2.1"


def create_app(settings: Settings | None = None) -> FastAPI:
    """Construct the API with all concrete dependencies wired explicitly."""

    resolved_settings: Settings = settings if settings is not None else get_settings()

    configure_logging(level=resolved_settings.log_level, log_format=resolved_settings.log_format)

    application = FastAPI(
        title=API_TITLE,
        version=API_VERSION,
        description="Governed retrieval and release workflows.",
        openapi_url="/v1/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    application.include_router(health_router)

    def custom_openapi() -> dict[str, Any]:
        if application.openapi_schema is not None:
            return application.openapi_schema

        schema = get_openapi(
            title=API_TITLE,
            version=API_VERSION,
            description=application.description,
            routes=application.routes,
            openapi_version=OPENAPI_VERSION,
        )

        application.openapi_schema = schema

        return schema

    application.openapi = custom_openapi

    return application
