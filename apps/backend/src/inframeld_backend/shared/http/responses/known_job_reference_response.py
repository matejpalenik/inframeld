from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class KnownJobReferenceResponse(BaseModel):
    """Identify original work without asserting its execution state or result."""

    model_config = ConfigDict(extra="forbid")
    job_id: UUID = Field(alias="jobId")
