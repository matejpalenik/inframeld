from dataclasses import replace
from uuid import UUID

import pytest

from inframeld_backend.access.application.commands.repair_stranded_authority_command import (
    RepairStrandedAuthorityCommand,
)
from inframeld_backend.access.application.dtos.action_grantor_repair_responsibility_dto import (
    ActionGrantorRepairResponsibilityDTO,
)
from inframeld_backend.access.application.dtos.project_grant_target_dto import ProjectGrantTargetDTO
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


def command() -> RepairStrandedAuthorityCommand:
    return RepairStrandedAuthorityCommand(
        expected_installation_id=InstallationId(UUID(int=4)),
        operation_id=OperationId("operator-original"),
        responsibility=ActionGrantorRepairResponsibilityDTO(
            ProjectGrantTargetDTO(ProjectId(UUID(int=3))), ActionId("edit-project-metadata")
        ),
        expected_access_revision=0,
        expected_identity_id=UUID(int=5),
        operator_label="Operator",
        reason="Repair metadata authority",
        identity_proof=HumanAccessTokenCredential("private-transient-token"),
    )


@pytest.mark.parametrize("revision", [-1, True, 1.5])
def test_repair_rejects_invalid_review_revision(revision: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        replace(command(), expected_access_revision=revision)  # type: ignore[arg-type]


def test_repair_requires_bounded_attribution_and_never_represents_the_token() -> None:
    assert "private-transient-token" not in repr(command())
    with pytest.raises(ValueError):
        replace(command(), operator_label=" ")
    with pytest.raises(ValueError):
        replace(command(), reason="a" * 513)
