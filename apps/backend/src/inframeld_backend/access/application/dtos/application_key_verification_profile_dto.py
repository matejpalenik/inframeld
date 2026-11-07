from dataclasses import dataclass

from inframeld_backend.access.domain.enums.application_key_adapter import ApplicationKeyAdapter
from inframeld_backend.access.domain.value_objects.application_key_audience import (
    ApplicationKeyAudience,
)


@dataclass(frozen=True, slots=True)
class ApplicationKeyVerificationProfileDTO:
    """Supply an independently configured audience and adapter, never request claims."""

    audience: ApplicationKeyAudience
    adapter: ApplicationKeyAdapter
