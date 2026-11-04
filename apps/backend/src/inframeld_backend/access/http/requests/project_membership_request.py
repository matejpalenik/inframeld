from pydantic import BaseModel, ConfigDict, Field


class ProjectMembershipRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    expected_access_revision: int = Field(
        alias="expectedAccessRevision", strict=True, ge=0, le=2**63 - 1
    )
