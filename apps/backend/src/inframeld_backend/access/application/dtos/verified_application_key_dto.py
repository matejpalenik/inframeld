from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.application_key_id import ApplicationKeyId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId


@dataclass(frozen=True, slots=True)
class VerifiedApplicationKeyDTO:
    """Identify the stored key and principal after complete credential verification."""

    key_id: ApplicationKeyId
    principal_id: PrincipalId
