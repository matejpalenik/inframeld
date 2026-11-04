from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class HumanAdmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    identity_id: UUID = Field(alias="identityId")
    expected_access_revision: int = Field(
        alias="expectedAccessRevision", strict=True, ge=0, le=2**63 - 1
    )
