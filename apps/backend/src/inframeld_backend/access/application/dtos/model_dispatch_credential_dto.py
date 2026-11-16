from dataclasses import dataclass, field

from inframeld_backend.access.application.dtos.encrypted_provider_credential_dto import (
    EncryptedProviderCredentialDTO,
)
from inframeld_backend.access.application.dtos.model_connection_access_dto import (
    ModelConnectionAccessDTO,
)
from inframeld_backend.access.application.dtos.provider_credential_binding_dto import (
    ProviderCredentialBindingDTO,
)


@dataclass(frozen=True, slots=True)
class ModelDispatchCredentialDTO:
    """Carry an exact current sealed slot within the private dispatch boundary."""

    access: ModelConnectionAccessDTO
    access_revision: int
    binding: ProviderCredentialBindingDTO
    envelope: EncryptedProviderCredentialDTO = field(repr=False)
