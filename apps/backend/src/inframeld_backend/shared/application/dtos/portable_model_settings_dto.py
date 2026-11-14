from dataclasses import dataclass

from inframeld_backend.shared.application.dtos.effective_model_settings_dto import (
    EffectiveModelSettingsDTO,
)
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName


@dataclass(frozen=True, slots=True)
class PortableModelSettingsDTO:
    """Carry effective settings with a Model Connection name resolved at the destination."""

    connection_name: str
    model: str
    effective: EffectiveModelSettingsDTO

    def __post_init__(self) -> None:
        ResourceName(self.connection_name)
        if not self.model.strip():
            raise ValueError("Portable model settings require an exact model.")
