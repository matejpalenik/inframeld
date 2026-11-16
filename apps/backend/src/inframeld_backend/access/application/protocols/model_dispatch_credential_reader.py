from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.admitted_work_authority_dto import (
    AdmittedWorkAuthorityDTO,
)
from inframeld_backend.access.application.dtos.encrypted_provider_credential_dto import (
    EncryptedProviderCredentialDTO,
)
from inframeld_backend.access.application.dtos.model_connection_access_dto import (
    ModelConnectionAccessDTO,
)
from inframeld_backend.access.application.dtos.provider_credential_binding_dto import (
    ProviderCredentialBindingDTO,
)
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId


class ModelDispatchCredentialReader(Protocol):
    """Observe exact connection Use and its current sealed slot in the caller transaction."""

    @abstractmethod
    async def read_access(
        self, authority: AdmittedWorkAuthorityDTO, connection_id: ModelConnectionId
    ) -> tuple[ModelConnectionAccessDTO, int] | None:
        """Return current Use-scoped settings and revision without fetching the sealed slot."""
        ...

    @abstractmethod
    async def read_sealed(
        self,
        authority: AdmittedWorkAuthorityDTO,
        connection_id: ModelConnectionId,
        access_revision: int,
    ) -> tuple[ProviderCredentialBindingDTO, EncryptedProviderCredentialDTO] | None:
        """Read the current slot only after checking the same connection's access and approval."""
        ...
