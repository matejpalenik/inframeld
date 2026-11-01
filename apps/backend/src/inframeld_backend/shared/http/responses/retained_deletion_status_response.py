from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool

from inframeld_backend.shared.domain.enums.job_status import JobStatus


class RetainedDeletionStatusResponse(BaseModel):
    """Expose retained content-free facts with explicit unknown completion and expiry."""

    model_config = ConfigDict(extra="forbid")

    outcome: Literal["retained"]
    operation_id: str = Field(alias="operationId", min_length=1, max_length=128, strict=True)
    job_state: JobStatus | None = Field(alias="jobState")
    admission_confirmed: StrictBool | None = Field(alias="admissionConfirmed")
    access_blocked: StrictBool | None = Field(alias="accessBlocked")
    application_shutdown_complete: StrictBool | None = Field(alias="applicationShutdownComplete")
    physical_cleanup_complete: StrictBool | None = Field(alias="physicalCleanupComplete")
    retention_expires_at: datetime | None = Field(alias="retentionExpiresAt")
