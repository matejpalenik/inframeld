from typing import Literal

from pydantic import BaseModel, Field

from inframeld_backend.access.application.enums.identity_recovery_evidence_type import (
    IdentityRecoveryEvidenceType,
)


class IdentityRecoveryNotificationResponse(BaseModel):
    schema_version: Literal[2] = Field(default=2, alias="schemaVersion")
    operation_id: str = Field(alias="operationId")
    event_type: IdentityRecoveryEvidenceType = Field(alias="eventType")
    recorded: Literal[True] = True
