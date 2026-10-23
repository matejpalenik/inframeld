from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


@dataclass(frozen=True, slots=True)
class CompletedSynchronousOperationDTO:
    """Carry validated completed replay metadata, without establishing current authority.

    IdempotencyService checks the stored shape before constructing this result.
    Created distinguishes completion of new work from a saved replay.
    """

    operation_id: OperationId
    created: bool
    replay_kind: Literal[
        OperationReplayKind.SAFE_RESULT,
        OperationReplayKind.ISSUED_SECRET,
        OperationReplayKind.ANSWER_RECEIPT,
    ]
    expires_at: datetime
