from dataclasses import dataclass

from inframeld_backend.access.domain.enums.application_key_adapter import ApplicationKeyAdapter
from inframeld_backend.access.domain.policies.application_key_lifetime_policy import (
    ApplicationKeyLifetimePolicy,
)
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.commands.command import Command
from inframeld_backend.shared.application.protocols.project_command import ProjectCommand
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


@dataclass(frozen=True, slots=True)
class IssueApplicationKeyCommand(Command, ProjectCommand):
    project_id: ProjectId
    application_principal_id: PrincipalId
    allowed_adapters: tuple[ApplicationKeyAdapter, ...]
    expected_access_revision: int
    expires_in_seconds: int | None = None

    def __post_init__(self) -> None:
        RevisionValidation.require(self.expected_access_revision)
        if (
            type(self.allowed_adapters) is not tuple
            or not 1 <= len(self.allowed_adapters) <= 2
            or any(type(adapter) is not ApplicationKeyAdapter for adapter in self.allowed_adapters)
            or len(set(self.allowed_adapters)) != len(self.allowed_adapters)
        ):
            raise ValueError("Application-key adapters require a nonempty unique supported tuple.")
        if self.expires_in_seconds is not None and (
            type(self.expires_in_seconds) is not int
            or not 0 < self.expires_in_seconds <= ApplicationKeyLifetimePolicy.MAXIMUM_SECONDS
        ):
            raise ValueError("Application-key lifetime requires positive exact whole seconds.")
