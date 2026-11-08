from pydantic import BaseModel, ConfigDict, Field


class InvitationActivationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    invitation_token: str = Field(alias="invitationToken", strict=True, repr=False)
