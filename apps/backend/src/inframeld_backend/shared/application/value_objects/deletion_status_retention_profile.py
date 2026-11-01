from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DeletionStatusRetentionProfile:
    """Capture selected policy without a clock, with a 30-day default and 90-day maximum.

    A shorter period represents an explicitly reviewed installation policy,
    never a per-request override or a rewrite of an existing capture.
    """

    days: int = 30
    policy_version: str = "ADR-0117/PD-KNOWLEDGE-02:v1"

    def __post_init__(self) -> None:
        if type(self.days) is not int:
            raise TypeError("Status retention requires a whole number of days.")
        if not 1 <= self.days <= 90:
            raise ValueError("Status retention must remain within the supported profile.")
        if self.policy_version != "ADR-0117/PD-KNOWLEDGE-02:v1":
            raise ValueError("The status retention policy is not supported.")
