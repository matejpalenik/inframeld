from dataclasses import dataclass
from datetime import datetime

from inframeld_backend.shared.application.value_objects.operation_id import OperationId


@dataclass(frozen=True, slots=True)
class AcceptedAsyncOperationDTO:
    """Record asynchronous admission, independently of the job's execution outcome.

    Created distinguishes first admission from replay. An absent expiry preserves
    active work, while a recorded expiry is returned unchanged.
    """

    operation_id: OperationId
    created: bool
    expires_at: datetime | None
