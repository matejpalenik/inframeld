from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.commands.command import Command
from inframeld_backend.shared.application.protocols.project_command import ProjectCommand
from inframeld_backend.shared.domain.value_objects.usd_amount import UsdAmount


@dataclass(frozen=True, slots=True)
class ChangeProjectSpendingPolicyCommand(Command, ProjectCommand):
    """Request a reviewed policy change without resetting accounting or operation limits."""

    project_id: ProjectId
    expected_policy_revision: int
    monthly_limit: UsdAmount | None

    def __post_init__(self) -> None:
        if type(self.expected_policy_revision) is not int or self.expected_policy_revision < 0:
            raise ValueError("A policy change requires a nonnegative reviewed revision.")
        if self.monthly_limit is not None and self.monthly_limit.value < 0:
            raise ValueError("A Project spending limit cannot be negative.")
