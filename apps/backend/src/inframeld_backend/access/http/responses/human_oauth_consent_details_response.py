from pydantic import BaseModel, Field

from inframeld_backend.access.domain.enums.human_oauth_scope import HumanOAuthScope


class HumanOAuthConsentDetailsResponse(BaseModel):
    """Display checked access to Alice, without granting authority for a later POST."""

    account_subject: str = Field(serialization_alias="accountSubject")
    installation: str
    client_id: str = Field(serialization_alias="clientId")
    requested_scopes: list[HumanOAuthScope] = Field(serialization_alias="requestedScopes")
    requested_audience: list[str] = Field(serialization_alias="requestedAudience")
    approval_required: bool = Field(serialization_alias="approvalRequired")
    remember_consent_seconds: int = Field(serialization_alias="rememberConsentSeconds")
