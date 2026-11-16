from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.model_dispatch_credential_dto import (
    ModelDispatchCredentialDTO,
)
from inframeld_backend.shared.application.dtos.admitted_embedding_call_dto import (
    AdmittedEmbeddingCallDTO,
)
from inframeld_backend.shared.application.dtos.embedding_dispatch_result_dto import (
    EmbeddingDispatchResultDTO,
)


class ModelEmbeddingAdapter(Protocol):
    """Validate one configured route and observe one original invocation."""

    @abstractmethod
    def prepare(self) -> None:
        """Check the isolated SDK profile before opening a database session."""
        ...

    @abstractmethod
    def require_supported(
        self, call: AdmittedEmbeddingCallDTO, credential: ModelDispatchCredentialDTO
    ) -> str:
        """Check mapping, origin and price compatibility without external I/O."""
        ...

    @abstractmethod
    async def embed(
        self,
        call: AdmittedEmbeddingCallDTO,
        credential: ModelDispatchCredentialDTO,
        *,
        dispatch_deadline: float,
    ) -> EmbeddingDispatchResultDTO:
        """Use after fresh commit acknowledgment and before the monotonic send deadline."""
        ...
