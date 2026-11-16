from abc import abstractmethod
from datetime import timedelta
from typing import Protocol

from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.dtos.model_dispatch_issuance_dto import (
    ModelDispatchIssuanceDTO,
)
from inframeld_backend.shared.application.value_objects.model_call_id import ModelCallId


class ModelDispatchIssuanceRepository(Protocol):
    """Keep the original issuance and job marker in the caller transaction."""

    @abstractmethod
    async def add(
        self, attempt: JobAttemptContextDTO, issuance: ModelDispatchIssuanceDTO
    ) -> timedelta:
        """Save a first issuance and marker and return the observed remaining job lease."""
        ...

    @abstractmethod
    async def get(self, call_id: ModelCallId) -> ModelDispatchIssuanceDTO | None:
        """Observe retained attribution without allowing another invocation."""
        ...

    @abstractmethod
    async def confirm(
        self, attempt: JobAttemptContextDTO, call_id: ModelCallId, checkpoint: bytes
    ) -> bool:
        """Confirm the known live effect. A canceled owner keeps its existing checkpoint."""
        ...
