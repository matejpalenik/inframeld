"""Register the public process-health HTTP endpoint."""

from fastapi import APIRouter

from inframeld_backend.shared.http.errors.problem_definitions import INTERNAL_ERROR_PROBLEM
from inframeld_backend.shared.http.errors.problem_openapi import problem_responses

router = APIRouter()


@router.get(
    "/health",
    tags=["health"],
    # Preserve the published schema while keeping internal purpose documentation.
    openapi_extra={"description": None},
    operation_id="getHealth",
    responses=problem_responses(INTERNAL_ERROR_PROBLEM),
)
async def health() -> dict[str, str]:
    """Report that the HTTP process can serve a request; database compatibility is checked at startup."""
    return {"status": "ok"}
