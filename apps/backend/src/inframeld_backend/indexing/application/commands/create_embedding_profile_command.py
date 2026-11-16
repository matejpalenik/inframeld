from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.commands.command import Command
from inframeld_backend.shared.application.dtos.effective_model_settings_dto import (
    EffectiveModelSettingsDTO,
)
from inframeld_backend.shared.application.dtos.model_selection_dto import ModelSelectionDTO
from inframeld_backend.shared.application.protocols.project_command import ProjectCommand
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateEmbeddingProfileCommand(Command, ProjectCommand):
    """Supply explicit settings and a token-bound identity already reviewed by the caller."""

    project_id: ProjectId
    name: ResourceName
    display_name: SubmittedDisplayName
    selection: ModelSelectionDTO
    effective: EffectiveModelSettingsDTO
