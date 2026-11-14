from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.encrypted_provider_credential_dto import (
    EncryptedProviderCredentialDTO,
)
from inframeld_backend.access.application.dtos.provider_credential_binding_dto import (
    ProviderCredentialBindingDTO,
)
from inframeld_backend.access.application.value_objects.provider_credential_value import (
    ProviderCredentialValue,
)


class ProviderCredentialCipher(Protocol):
    """Require a trusted deployment key or seal one bound outgoing credential."""

    @abstractmethod
    def require_key(self, current_key_id: str | None) -> None: ...

    @abstractmethod
    def encrypt(
        self,
        value: ProviderCredentialValue,
        binding: ProviderCredentialBindingDTO,
        current_key_id: str | None,
    ) -> EncryptedProviderCredentialDTO: ...
