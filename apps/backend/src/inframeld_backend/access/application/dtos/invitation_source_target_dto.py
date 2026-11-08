from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class InvitationSourceTargetDTO:
    source_id: UUID
