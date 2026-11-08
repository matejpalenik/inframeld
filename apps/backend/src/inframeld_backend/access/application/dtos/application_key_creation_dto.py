from dataclasses import dataclass, field

from inframeld_backend.access.application.dtos.application_key_issuance_record_dto import (
    ApplicationKeyIssuanceRecordDTO,
)
from inframeld_backend.access.domain.value_objects.application_key_audience import (
    ApplicationKeyAudience,
)


@dataclass(frozen=True, slots=True)
class ApplicationKeyCreationDTO:
    """Pass verifier and trusted bindings to persistence without plaintext."""

    original: ApplicationKeyIssuanceRecordDTO
    verifier: bytes = field(repr=False)
    http_audience: ApplicationKeyAudience | None
    mcp_audience: ApplicationKeyAudience | None
