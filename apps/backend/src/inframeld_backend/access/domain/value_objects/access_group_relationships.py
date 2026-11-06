from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AccessGroupRelationships:
    """Observe ordinary membership and the management subset independently."""

    member: bool
    manager: bool

    def __post_init__(self) -> None:
        if type(self.member) is not bool or type(self.manager) is not bool:
            raise TypeError("Group relationships require exact boolean observations.")
        if self.manager and not self.member:
            raise ValueError("An access-group manager must also be an ordinary member.")
