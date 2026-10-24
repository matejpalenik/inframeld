"""Carry the authenticated local actor into application operations."""

from dataclasses import dataclass

from inframeld_backend.access.application.dtos.application_key_authentication_dto import (
    ApplicationKeyAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.browser_session_authentication_dto import (
    BrowserSessionAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId


@dataclass(frozen=True, slots=True)
class AccessContextDTO:
    """Carry the authenticated actor and complete evidence for its credential family.

    Authenticators construct this record after verification. Its evidence contains
    no credential secret, current account state or granted permissions.
    """

    actor_principal_id: PrincipalId
    authentication_evidence: (
        BrowserSessionAuthenticationDTO
        | HumanOAuthCredentialBindingDTO
        | ApplicationKeyAuthenticationDTO
    )

    def __post_init__(self) -> None:
        self._require_evidence(self.authentication_evidence)

    @staticmethod
    def _require_evidence(evidence: object) -> None:
        if not isinstance(
            evidence,
            (
                BrowserSessionAuthenticationDTO,
                HumanOAuthCredentialBindingDTO,
                ApplicationKeyAuthenticationDTO,
            ),
        ):
            raise TypeError("An access context requires recognized authentication evidence.")
