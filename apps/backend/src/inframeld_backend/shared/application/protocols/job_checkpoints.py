from abc import abstractmethod
from typing import Protocol

from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO


class JobCheckpoints(Protocol):
    """Guard bounded handler steps through fresh authority and current ownership.

    Calls finish their short transaction before returning. Check before each
    protected step. Non-repeatable external work requires a committed pending
    effect before dispatch and an exact confirmation afterward. These checks
    do not replace the owning handler's current source/resource authority.
    """

    @abstractmethod
    async def check(self, context: JobAttemptContextDTO) -> None: ...

    @abstractmethod
    async def save(self, context: JobAttemptContextDTO, data: bytes) -> None: ...

    @abstractmethod
    async def begin_effect(self, context: JobAttemptContextDTO, effect_id: str) -> None: ...

    @abstractmethod
    async def confirm_effect(
        self, context: JobAttemptContextDTO, effect_id: str, data: bytes
    ) -> None: ...

    @abstractmethod
    async def succeed(self, context: JobAttemptContextDTO) -> None: ...

    @abstractmethod
    async def fail(self, context: JobAttemptContextDTO) -> None: ...
