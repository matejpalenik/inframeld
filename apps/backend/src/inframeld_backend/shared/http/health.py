from fastapi import APIRouter

router = APIRouter()


@router.get("/health", tags=["health"], operation_id="getHealth")
async def health() -> dict[str, str]:
    return {"status": "ok"}
