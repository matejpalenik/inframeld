from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class InvitationEmbeddingProfileTargetDTO:
    embedding_profile_id: UUID
