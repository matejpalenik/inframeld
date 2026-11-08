from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class InvitationModelConnectionTargetDTO:
    model_connection_id: UUID
