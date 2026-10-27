from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HumanCredentialVersion:
    """Identify the current generation of one human's CLI credentials."""

    value: int

    def __post_init__(self) -> None:
        if type(self.value) is not int or not 1 <= self.value <= 2**63 - 1:
            raise ValueError("A credential version must be a positive BIGINT integer.")
