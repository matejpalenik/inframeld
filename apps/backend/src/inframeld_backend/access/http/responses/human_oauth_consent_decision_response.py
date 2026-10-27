from pydantic import BaseModel, Field


class HumanOAuthConsentDecisionResponse(BaseModel):
    redirect_to: str = Field(serialization_alias="redirectTo", repr=False)
