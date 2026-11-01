import json
from uuid import UUID

import pytest

from inframeld_backend.access.cli.errors.project_metadata_maintenance_input_error import (
    ProjectMetadataMaintenanceInputError,
)
from inframeld_backend.access.cli.mappers.project_metadata_maintenance_mapper import (
    ProjectMetadataMaintenanceMapper,
)


def payload() -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "mode": "repair-stranded-authority",
        "expectedInstallationId": str(UUID(int=4)),
        "operationId": "operator-original",
        "operatorLabel": "Operator",
        "reason": "Repair metadata authority",
        "expectedAccessRevision": 0,
        "expectedIdentityId": str(UUID(int=5)),
        "identityProof": {"kind": "hydra-access-token", "accessToken": "private-proof"},
        "responsibility": {
            "kind": "action-grantor",
            "target": {"kind": "project", "projectId": str(UUID(int=3))},
            "actionId": "edit-project-metadata",
        },
    }


def test_exact_metadata_responsibility_maps_without_retaining_plaintext_in_representations() -> (
    None
):
    command = ProjectMetadataMaintenanceMapper.read(json.dumps(payload()).encode())
    assert command.project_id.value == UUID(int=3)
    assert command.expected_identity_id == UUID(int=5)
    assert "private-proof" not in repr(command)


@pytest.mark.parametrize(
    "field,value",
    [
        ("schemaVersion", 1.0),
        ("expectedAccessRevision", True),
        ("mode", "bootstrap-first-administrator"),
        (
            "responsibility",
            {
                "kind": "group-manager",
                "projectId": str(UUID(int=3)),
                "accessGroupId": str(UUID(int=9)),
            },
        ),
        (
            "responsibility",
            {
                "kind": "action-grantor",
                "target": {"kind": "project", "projectId": str(UUID(int=3))},
                "actionId": "manage-project-members",
            },
        ),
    ],
)
def test_other_modes_actions_and_noninteger_tokens_are_rejected_with_safe_correlation(
    field: str, value: object
) -> None:
    request = payload()
    request[field] = value
    with pytest.raises(ProjectMetadataMaintenanceInputError) as failure:
        ProjectMetadataMaintenanceMapper.read(json.dumps(request).encode())
    assert (
        failure.value.operation_id is not None
        and failure.value.operation_id.value == "operator-original"
    )
    assert "private-proof" not in str(failure.value)
