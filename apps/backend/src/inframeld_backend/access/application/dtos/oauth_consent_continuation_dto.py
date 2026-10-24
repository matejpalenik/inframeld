from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class OAuthConsentContinuationDTO:
    """Return Hydra's checked continuation privately - it can contain flow secrets."""

    redirect_to: str = field(repr=False)
