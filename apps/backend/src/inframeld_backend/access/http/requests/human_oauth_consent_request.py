from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from inframeld_backend.access.application.enums.oauth_consent_decision import OAuthConsentDecision
from inframeld_backend.access.application.value_objects.oauth_consent_challenge import (
    OAuthConsentChallenge,
)


class HumanOAuthConsentRequest(BaseModel):
    """Choose a consent decision - account, access and lifetime come from the server."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    consent_challenge: SecretStr = Field(alias="consentChallenge", min_length=1)
    decision: OAuthConsentDecision
    remember: bool = Field(default=False, strict=True)

    @field_validator("consent_challenge")
    @classmethod
    def _validate_challenge(cls, value: SecretStr) -> SecretStr:
        OAuthConsentChallenge(value.get_secret_value())
        return value
