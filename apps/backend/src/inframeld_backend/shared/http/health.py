from fastapi import APIRouter

from inframeld_backend.shared.http.problem_definitions import INTERNAL_ERROR_PROBLEM
from inframeld_backend.shared.http.problem_openapi import problem_responses

router = APIRouter()


@router.get(
    "/health",
    tags=["health"],
    operation_id="getHealth",
    responses=problem_responses(INTERNAL_ERROR_PROBLEM),
)
async def health() -> dict[str, str]:
    return {"status": "ok"}
