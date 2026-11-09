import json
from uuid import UUID

import pytest

from inframeld_backend.access.application.dtos.access_group_grant_target_dto import (
    AccessGroupGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.action_grantor_repair_responsibility_dto import (
    ActionGrantorRepairResponsibilityDTO,
)
from inframeld_backend.access.application.dtos.application_account_grant_target_dto import (
    ApplicationAccountGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.group_manager_repair_responsibility_dto import (
    GroupManagerRepairResponsibilityDTO,
)
from inframeld_backend.access.application.dtos.organization_grant_target_dto import (
    OrganizationGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.project_grant_target_dto import ProjectGrantTargetDTO
from inframeld_backend.access.application.dtos.stranded_authority_repair_result_dto import (
    StrandedAuthorityRepairResultDTO,
)
from inframeld_backend.access.cli.errors.stranded_authority_maintenance_input_error import (
    StrandedAuthorityMaintenanceInputError,
)
from inframeld_backend.access.cli.mappers.stranded_authority_maintenance_mapper import (
    StrandedAuthorityMaintenanceMapper,
)
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


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
    command = StrandedAuthorityMaintenanceMapper.read(json.dumps(payload()).encode())
    assert command.responsibility == ActionGrantorRepairResponsibilityDTO(
        ProjectGrantTargetDTO(ProjectId(UUID(int=3))), ActionId("edit-project-metadata")
    )
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
            },
        ),
        (
            "responsibility",
            {
                "kind": "action-grantor",
                "target": {"kind": "project", "projectId": str(UUID(int=3))},
                "actionId": "run-pipeline",
            },
        ),
    ],
)
def test_other_modes_actions_and_noninteger_tokens_are_rejected_with_safe_correlation(
    field: str, value: object
) -> None:
    request = payload()
    request[field] = value
    with pytest.raises(StrandedAuthorityMaintenanceInputError) as failure:
        StrandedAuthorityMaintenanceMapper.read(json.dumps(request).encode())
    assert (
        failure.value.operation_id is not None
        and failure.value.operation_id.value == "operator-original"
    )
    assert "private-proof" not in str(failure.value)


@pytest.mark.parametrize(
    "responsibility,expected",
    [
        (
            {
                "kind": "group-manager",
                "projectId": str(UUID(int=3)),
                "accessGroupId": str(UUID(int=9)),
            },
            GroupManagerRepairResponsibilityDTO(ProjectId(UUID(int=3)), AccessGroupId(UUID(int=9))),
        ),
        (
            {
                "kind": "action-grantor",
                "target": {"kind": "organization", "organizationId": str(UUID(int=2))},
                "actionId": "suspend-users",
            },
            ActionGrantorRepairResponsibilityDTO(
                OrganizationGrantTargetDTO(OrganizationId(UUID(int=2))), ActionId("suspend-users")
            ),
        ),
        (
            {
                "kind": "action-grantor",
                "target": {"kind": "project", "projectId": str(UUID(int=3))},
                "actionId": "manage-project-members",
            },
            ActionGrantorRepairResponsibilityDTO(
                ProjectGrantTargetDTO(ProjectId(UUID(int=3))), ActionId("manage-project-members")
            ),
        ),
        (
            {
                "kind": "action-grantor",
                "target": {"kind": "project", "projectId": str(UUID(int=3))},
                "actionId": "edit-project-metadata",
            },
            ActionGrantorRepairResponsibilityDTO(
                ProjectGrantTargetDTO(ProjectId(UUID(int=3))), ActionId("edit-project-metadata")
            ),
        ),
        (
            {
                "kind": "action-grantor",
                "target": {
                    "kind": "access-group",
                    "projectId": str(UUID(int=3)),
                    "accessGroupId": str(UUID(int=9)),
                },
                "actionId": "add-documents",
            },
            ActionGrantorRepairResponsibilityDTO(
                AccessGroupGrantTargetDTO(ProjectId(UUID(int=3)), AccessGroupId(UUID(int=9))),
                ActionId("add-documents"),
            ),
        ),
        (
            {
                "kind": "action-grantor",
                "target": {
                    "kind": "application-account",
                    "projectId": str(UUID(int=3)),
                    "applicationPrincipalId": str(UUID(int=8)),
                },
                "actionId": "revoke-application-keys",
            },
            ActionGrantorRepairResponsibilityDTO(
                ApplicationAccountGrantTargetDTO(ProjectId(UUID(int=3)), PrincipalId(UUID(int=8))),
                ActionId("revoke-application-keys"),
            ),
        ),
    ],
)
def test_new_access_responsibilities_retain_exact_typed_scope_and_secret_custody(
    responsibility: dict[str, object],
    expected: GroupManagerRepairResponsibilityDTO | ActionGrantorRepairResponsibilityDTO,
) -> None:
    request = payload()
    request["responsibility"] = responsibility
    command = StrandedAuthorityMaintenanceMapper.read(json.dumps(request).encode())
    assert command.responsibility == expected
    assert command.expected_identity_id == UUID(int=5)
    assert command.expected_access_revision == 0
    assert command.operation_id.value == "operator-original"
    assert "private-proof" not in repr(command)
    result = StrandedAuthorityRepairResultDTO(
        command.operation_id,
        command.expected_installation_id,
        OrganizationId(UUID(int=2)),
        expected,
        PrincipalId(UUID(int=1)),
        1,
    )
    assert StrandedAuthorityMaintenanceMapper.result(result) == {
        "schemaVersion": 1,
        "mode": "repair-stranded-authority",
        "operationId": "operator-original",
        "installationId": str(UUID(int=4)),
        "principalId": str(UUID(int=1)),
        "accessRevision": 1,
        "outcome": "repaired",
        "responsibility": responsibility,
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("schemaVersion", True),
        ("schemaVersion", 1.0),
        ("schemaVersion", 2),
        ("expectedAccessRevision", True),
        ("expectedAccessRevision", 1.0),
        ("expectedAccessRevision", -1),
        ("expectedAccessRevision", 2**53),
        ("expectedIdentityId", "not-a-uuid"),
        ("operatorLabel", " "),
        ("reason", ""),
        ("operationId", "x" * 129),
        ("mode", "bootstrap-first-administrator"),
        ("unexpected", True),
        ("identityProof", {"kind": "refresh-token", "accessToken": "private-proof"}),
        (
            "identityProof",
            {"kind": "hydra-access-token", "accessToken": "private-proof", "extra": True},
        ),
        (
            "responsibility",
            {
                "kind": "group-manager",
                "projectId": str(UUID(int=3)),
                "accessGroupId": str(UUID(int=9)),
                "actionId": "add-documents",
            },
        ),
        ("responsibility", {"kind": "group-manager", "projectId": str(UUID(int=3))}),
        (
            "responsibility",
            {
                "kind": "action-grantor",
                "target": {"kind": "organization", "organizationId": str(UUID(int=2))},
                "actionId": "add-documents",
            },
        ),
        (
            "responsibility",
            {
                "kind": "action-grantor",
                "target": {"kind": "project", "projectId": str(UUID(int=3))},
                "actionId": "arbitrary-action",
            },
        ),
        (
            "responsibility",
            {
                "kind": "action-grantor",
                "target": {
                    "kind": "access-group",
                    "projectId": str(UUID(int=3)),
                    "accessGroupId": str(UUID(int=9)),
                },
                "actionId": "issue-application-keys",
            },
        ),
        (
            "responsibility",
            {
                "kind": "action-grantor",
                "target": {
                    "kind": "application-account",
                    "projectId": str(UUID(int=3)),
                    "applicationPrincipalId": str(UUID(int=8)),
                },
                "actionId": "delete-documents",
            },
        ),
        (
            "responsibility",
            {
                "kind": "action-grantor",
                "target": {"kind": "pipeline", "pipelineId": str(UUID(int=9))},
                "actionId": "execute-query",
            },
        ),
        (
            "responsibility",
            {
                "kind": "action-grantor",
                "target": {
                    "kind": "project",
                    "projectId": str(UUID(int=3)),
                    "organizationId": str(UUID(int=2)),
                },
                "actionId": "edit-project-metadata",
            },
        ),
    ],
)
def test_new_repair_input_rejects_changed_or_unsupported_meaning_without_echoing_proof(
    field: str,
    value: object,
) -> None:
    request = payload()
    request[field] = value
    with pytest.raises(StrandedAuthorityMaintenanceInputError) as failure:
        StrandedAuthorityMaintenanceMapper.read(json.dumps(request).encode())
    if field == "operationId":
        assert failure.value.operation_id is None
    else:
        assert failure.value.operation_id is not None
        assert failure.value.operation_id.value == "operator-original"
    assert "private-proof" not in str(failure.value)


@pytest.mark.parametrize("suffix", [b" {}", b"\nnull"])
def test_new_repair_input_rejects_multiple_json_values(suffix: bytes) -> None:
    with pytest.raises(StrandedAuthorityMaintenanceInputError):
        StrandedAuthorityMaintenanceMapper.read(json.dumps(payload()).encode() + suffix)


def test_new_repair_input_rejects_duplicate_keys_and_oversized_received_bytes() -> None:
    request = json.dumps(payload()).encode()
    duplicate = request.replace(b'"schemaVersion": 1', b'"schemaVersion": 1, "schemaVersion": 1')
    for invalid in (duplicate, request + b" " * 65536):
        with pytest.raises(StrandedAuthorityMaintenanceInputError):
            StrandedAuthorityMaintenanceMapper.read(invalid)
