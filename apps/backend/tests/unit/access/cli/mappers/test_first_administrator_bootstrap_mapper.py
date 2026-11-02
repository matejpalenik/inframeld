import json
from uuid import UUID

import pytest

from inframeld_backend.access.application.dtos.first_administrator_bootstrap_result_dto import (
    FirstAdministratorBootstrapResultDTO,
)
from inframeld_backend.access.cli.errors.project_metadata_maintenance_input_error import (
    ProjectMetadataMaintenanceInputError,
)
from inframeld_backend.access.cli.mappers.first_administrator_bootstrap_mapper import (
    FirstAdministratorBootstrapMapper,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


def request() -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "mode": "bootstrap-first-administrator",
        "expectedInstallationId": str(UUID(int=1)),
        "operationId": "first-claim",
        "operatorLabel": "Host operator",
        "reason": "Establish the installation",
        "expectedAccessRevision": 0,
        "expectedIdentityId": str(UUID(int=2)),
        "identityProof": {"kind": "hydra-access-token", "accessToken": "private-proof"},
    }


def test_reads_only_the_fixed_bootstrap_intent_and_keeps_proof_out_of_repr() -> None:
    command = FirstAdministratorBootstrapMapper.read(json.dumps(request()).encode())

    assert command.expected_installation_id == InstallationId(UUID(int=1))
    assert command.expected_identity_id == UUID(int=2)
    assert command.operation_id == OperationId("first-claim")
    assert command.expected_access_revision == 0
    assert command.identity_proof.value == "private-proof"
    assert "private-proof" not in repr(command)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schemaVersion", True),
        ("schemaVersion", 1.0),
        ("mode", "repair-stranded-authority"),
        ("expectedInstallationId", "invalid-installation"),
        ("expectedIdentityId", "invalid-identity"),
        ("expectedAccessRevision", True),
        ("expectedAccessRevision", 0.0),
        ("expectedAccessRevision", -1),
        ("expectedAccessRevision", 2**63),
        ("operationId", " "),
        ("operationId", "x" * 129),
        ("operatorLabel", "x" * 129),
        ("reason", "x" * 513),
        ("reason", "unsafe\x00input"),
        ("identityProof", {"kind": "id-token", "accessToken": "private-proof"}),
        ("identityProof", {"kind": "hydra-access-token", "accessToken": ""}),
        (
            "identityProof",
            {"kind": "hydra-access-token", "accessToken": "private-proof", "extra": True},
        ),
    ],
)
def test_rejects_changed_or_unbounded_bootstrap_meaning(field: str, value: object) -> None:
    values = request() | {field: value}

    with pytest.raises(ProjectMetadataMaintenanceInputError) as error:
        FirstAdministratorBootstrapMapper.read(json.dumps(values).encode())

    assert "private-proof" not in str(error.value)


@pytest.mark.parametrize("field", ["responsibility", "organizationName", "principalId"])
def test_cannot_choose_assignments_or_organization_through_extra_fields(field: str) -> None:
    with pytest.raises(ProjectMetadataMaintenanceInputError):
        FirstAdministratorBootstrapMapper.read(
            json.dumps(request() | {field: "untrusted"}).encode()
        )


@pytest.mark.parametrize(
    "payload",
    [
        b"\xff",
        b'{"schemaVersion":1,"schemaVersion":1}',
        b"{} {}",
        b'{"schemaVersion":NaN}',
        b" " * 65_537,
    ],
    ids=["invalid-utf8", "duplicate-key", "second-value", "nonfinite", "oversized"],
)
def test_rejects_malformed_duplicate_or_oversized_input_without_echo(payload: bytes) -> None:
    with pytest.raises(ProjectMetadataMaintenanceInputError):
        FirstAdministratorBootstrapMapper.read(payload)


def test_output_contains_only_the_original_safe_bootstrap_result() -> None:
    result = FirstAdministratorBootstrapResultDTO(
        OperationId("first-claim"),
        InstallationId(UUID(int=1)),
        OrganizationId(UUID(int=3)),
        PrincipalId(UUID(int=4)),
        1,
    )

    assert FirstAdministratorBootstrapMapper.result(result) == {
        "schemaVersion": 1,
        "mode": "bootstrap-first-administrator",
        "operationId": "first-claim",
        "installationId": str(UUID(int=1)),
        "principalId": str(UUID(int=4)),
        "accessRevision": 1,
        "outcome": "bootstrapped",
    }
