from pydantic import BaseModel, ConfigDict, Field

from inframeld_backend.shared.http.types.model_decimal import ModelDecimal


class ModelRateRequest(BaseModel):
    """Parse an exact spending rate in its original category and unit."""

    model_config = ConfigDict(extra="forbid", strict=True)

    category: str = Field(pattern=r"\S")
    unit: str = Field(pattern=r"\S")
    usd_per_unit: ModelDecimal = Field(ge=0)
