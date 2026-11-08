from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class InvitationProcessingProfileTargetDTO:
    processing_profile_id: UUID
