from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from inframeld_backend.shared.application.dtos.spending_usage_dto import SpendingUsageDTO
from inframeld_backend.shared.application.enums.spending_observation_kind import (
    SpendingObservationKind,
)
from inframeld_backend.shared.application.value_objects.model_call_id import ModelCallId
from inframeld_backend.shared.domain.validation.value_validation import ValueValidation


@dataclass(frozen=True, slots=True)
class SpendingObservationDTO:
    """Carry call-bound evidence supplied by the trusted owning application path.

    References and types do not authenticate provider evidence. This internal
    record contains no provider body, prompt, credential or public correction input.
    """

    evidence_id: UUID
    call_id: ModelCallId
    kind: SpendingObservationKind
    observed_at: datetime
    source_reference: str
    usage: tuple[SpendingUsageDTO, ...] | None = None
    charge: Decimal | None = None

    def __post_init__(self) -> None:
        ValueValidation.require_uuid(self.evidence_id)
        self._require_call_id(self.call_id)
        if not self.source_reference.strip():
            raise ValueError("An observation requires a call-bound source reference.")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("An observation requires an aware observation time.")
        if self.kind == SpendingObservationKind.CHARGE:
            if not isinstance(self.charge, Decimal) or self.usage is not None:
                raise ValueError("Charge evidence requires only an exact monetary amount.")
            if not self.charge.is_finite() or self.charge < 0:
                raise ValueError("A charge must be finite and nonnegative.")
        elif self.kind == SpendingObservationKind.USAGE:
            if self.usage is None or self.charge is not None:
                raise ValueError("Usage evidence requires only canonical usage.")
            keys = {(usage.category, usage.unit) for usage in self.usage}
            if not keys or len(keys) != len(self.usage):
                raise ValueError("Usage evidence requires unique category and unit keys.")
        elif self.kind in (
            SpendingObservationKind.NOT_SENT,
            SpendingObservationKind.NOT_BILLED,
            SpendingObservationKind.UNCERTAIN,
        ):
            if self.usage is not None or self.charge is not None:
                raise ValueError("Outcome evidence cannot carry an accounting amount.")
        else:
            raise ValueError("Unsupported spending evidence kind.")

    @staticmethod
    def _require_call_id(value: object) -> None:
        if not isinstance(value, ModelCallId):
            raise TypeError("An observation requires its original call identifier.")
