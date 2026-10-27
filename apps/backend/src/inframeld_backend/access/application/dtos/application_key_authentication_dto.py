from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.application_key_id import ApplicationKeyId


@dataclass(frozen=True, slots=True)
class ApplicationKeyAuthenticationDTO:
    """Identify the key used for application authentication, without its secret.

    This record does not verify a key. Production key authentication remains unfinished.
    """

    key_id: ApplicationKeyId
