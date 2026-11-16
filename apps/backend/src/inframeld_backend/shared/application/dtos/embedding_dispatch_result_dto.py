from dataclasses import dataclass, field
from typing import Literal

from inframeld_backend.shared.application.enums.spending_observation_kind import (
    SpendingObservationKind,
)


@dataclass(frozen=True, slots=True)
class EmbeddingDispatchResultDTO:
    """Describe bounded adapter evidence without retaining an upstream body or credential."""

    kind: Literal[
        SpendingObservationKind.USAGE,
        SpendingObservationKind.NOT_SENT,
        SpendingObservationKind.UNCERTAIN,
    ]
    vector: tuple[float, ...] | None = field(default=None, repr=False)
    prompt_tokens: int | None = None
    provider_reference: str | None = None
    response_status: int | None = None
