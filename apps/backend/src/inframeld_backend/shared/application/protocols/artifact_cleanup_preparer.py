from abc import abstractmethod
from typing import Protocol

from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.dtos.job_effect_binding_dto import JobEffectBindingDTO


class ArtifactCleanupPreparer(Protocol):
    """Prepare one original abandoned-staging DELETE before leaving its short transaction.

    A binding returns only after its exact invocation and pending unit commit.
    It grants no native admission or abort proof. Preserve the original job,
    payload, attempt, fence and work deadline, using the locked stored checkpoint.

    None means the live original obligation and single target already have an
    exact committed DELETE acknowledgment and no unresolved pending unit.
    Missing, malformed, foreign or unavailable state raises instead. Neither
    result proves remote absence, physical retirement or released capacity.

    The acknowledgment checkpoint is the marker artifact.cleanup.delete-ack.v1,
    a NUL byte, then the original obligation, artifact and attempt UUID bytes.
    Match it against protected current facts, not the caller's resume bytes.
    """

    @abstractmethod
    async def prepare(self, context: JobAttemptContextDTO) -> JobEffectBindingDTO | None: ...
