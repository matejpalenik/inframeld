from collections.abc import Callable
from typing import Annotated
from urllib.parse import unquote, urlsplit

from fastapi import APIRouter, HTTPException, Path, Response

from inframeld_backend.access.application.dtos.public_discovery_dto import PublicDiscoveryDTO
from inframeld_backend.access.http.responses.inframeld_discovery_response import (
    InframeldDiscoveryResponse,
)
from inframeld_backend.access.http.responses.protected_resource_metadata_response import (
    ProtectedResourceMetadataResponse,
)
from inframeld_backend.shared.http.definitions.problem_catalogue import (
    DEPENDENCY_UNAVAILABLE_PROBLEM,
    RESOURCE_NOT_FOUND_PROBLEM,
    VALIDATION_ERROR_PROBLEM,
)
from inframeld_backend.shared.http.openapi.problem_openapi import problem_responses


def create_discovery_router(descriptor: Callable[[], PublicDiscoveryDTO | None]) -> APIRouter:
    """Serve only the configured resource, independent of request host and authentication."""
    router = APIRouter(tags=["discovery"])

    def publish(response: Response, resource_path: str) -> ProtectedResourceMetadataResponse:
        snapshot = descriptor()
        if snapshot is None:
            raise HTTPException(status_code=503)

        path = unquote(urlsplit(snapshot.resource).path).removeprefix("/")
        if resource_path != path:
            raise HTTPException(status_code=404)

        response.headers["Cache-Control"] = "no-store"
        return ProtectedResourceMetadataResponse(
            resource=snapshot.resource,
            authorization_servers=(snapshot.issuer,),
            scopes_supported=("inframeld:api",),
            bearer_methods_supported=("header",),
            inframeld=InframeldDiscoveryResponse(
                schema_version=1,
                client_id="inframeld-cli",
                installation_id=snapshot.installation_id.value,
            ),
        )

    @router.get(
        "/.well-known/oauth-protected-resource",
        operation_id="getProtectedResourceMetadata",
        responses=(
            problem_responses(DEPENDENCY_UNAVAILABLE_PROBLEM)
            | problem_responses(RESOURCE_NOT_FOUND_PROBLEM)
            | problem_responses(VALIDATION_ERROR_PROBLEM)
        ),
    )
    async def root_metadata(response: Response) -> ProtectedResourceMetadataResponse:
        """Read anonymous public metadata for a root API identity."""
        return publish(response, "")

    @router.get(
        "/.well-known/oauth-protected-resource/{resource_path:path}",
        operation_id="getProtectedResourceMetadataForPath",
        responses=(
            problem_responses(DEPENDENCY_UNAVAILABLE_PROBLEM)
            | problem_responses(RESOURCE_NOT_FOUND_PROBLEM)
            | problem_responses(VALIDATION_ERROR_PROBLEM)
        ),
    )
    async def path_metadata(
        resource_path: Annotated[
            str,
            Path(
                description="Percent-encoded relative resource path. Preserve slash separators and existing percent escapes.",
                json_schema_extra={"x-inframeld-encoded-path": True},
            ),
        ],
        response: Response,
    ) -> ProtectedResourceMetadataResponse:
        """Read anonymous public metadata for the exact configured API path."""
        return publish(response, resource_path)

    return router
