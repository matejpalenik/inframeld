from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class InvitationPipelineTargetDTO:
    pipeline_id: UUID
