from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

API_TITLE = "Inframeld API"
API_VERSION = "0.1.0"
OPENAPI_VERSION = "3.0.3"


def create_app() -> FastAPI:
    application = FastAPI(
        title=API_TITLE,
        version=API_VERSION,
        description="Governed retrieval and release workflows.",
        openapi_url="/v1/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    @application.get("/health", tags=["health"], operation_id="getHealth")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

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


app = create_app()
