from dataclasses import dataclass

from inframeld_backend.access.application.dtos.identity_recovery_admission_dto import (
    IdentityRecoveryAdmissionDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_session_binding_dto import (
    IdentityRecoverySessionBindingDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_settings_binding_dto import (
    IdentityRecoverySettingsBindingDTO,
)
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)


@dataclass(frozen=True, slots=True)
class IdentityRecoveryAssociationFactsDTO:
    """Observe stored bindings for one settings notification without deciding its meaning."""

    source_admission: IdentityRecoveryAdmissionDTO | None
    session_binding: IdentityRecoverySessionBindingDTO | None
    session_admission: IdentityRecoveryAdmissionDTO | None
    settings_binding: IdentityRecoverySettingsBindingDTO | None
    settings_admission: IdentityRecoveryAdmissionDTO | None
    current_version: HumanCredentialVersion | None
