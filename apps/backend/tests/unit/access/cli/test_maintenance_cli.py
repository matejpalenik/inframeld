import io
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import override
from uuid import UUID

import pytest

from inframeld_backend.access.application.commands.bootstrap_first_administrator_command import (
    BootstrapFirstAdministratorCommand,
)
from inframeld_backend.access.application.commands.human_suspension_cleanup_maintenance_command import (
    HumanSuspensionCleanupMaintenanceCommand,
)
from inframeld_backend.access.application.commands.repair_stranded_authority_command import (
    RepairStrandedAuthorityCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.action_grantor_repair_responsibility_dto import (
    ActionGrantorRepairResponsibilityDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.project_grant_target_dto import ProjectGrantTargetDTO
from inframeld_backend.access.application.dtos.stranded_authority_repair_result_dto import (
    StrandedAuthorityRepairResultDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.human_suspension_cleanup_maintenance_intent import (
    HumanSuspensionCleanupMaintenanceIntent,
)
from inframeld_backend.access.application.protocols.human_access_token_authenticator import (
    HumanAccessTokenAuthenticator,
)
from inframeld_backend.access.application.protocols.stranded_authority_repairer import (
    StrandedAuthorityRepairer,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.cli.errors.stranded_authority_maintenance_input_error import (
    StrandedAuthorityMaintenanceInputError,
)
from inframeld_backend.access.cli.maintenance_cli import MaintenanceCli
from inframeld_backend.access.cli.stranded_authority_maintenance_cli import (
    StrandedAuthorityMaintenanceCli,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.errors.application_errors import (
    AuthenticationRequiredError,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


class MockProofAuthenticator(HumanAccessTokenAuthenticator):
    def __init__(self, events: list[str], *, reject: bool = False) -> None:
        self.events = events
        self.reject = reject

    @override
    async def authenticate(self, credential: HumanAccessTokenCredential | None) -> AccessContextDTO:
        self.events.append("verify-proof")
        if self.reject:
            raise AuthenticationRequiredError()
        identity = VerifiedHumanIdentityDTO(
            IdentityAuthority("kratos:test"), IdentitySubject(str(UUID(int=5)))
        )
        return AccessContextDTO(
            PrincipalId(UUID(int=1)),
            HumanOAuthCredentialBindingDTO(
                identity, InstallationId(UUID(int=4)), HumanCredentialVersion(1)
            ),
        )


class MockRepairOperation(StrandedAuthorityRepairer):
    def __init__(self, events: list[str]) -> None:
        self.events = events

    @override
    async def repair(
        self, *, access: AccessContextDTO, command: RepairStrandedAuthorityCommand
    ) -> StrandedAuthorityRepairResultDTO:
        self.events.append("repair")
        return StrandedAuthorityRepairResultDTO(
            operation_id=command.operation_id,
            installation_id=command.expected_installation_id,
            organization_id=OrganizationId(UUID(int=2)),
            responsibility=command.responsibility,
            recipient_id=access.actor_principal_id,
            access_revision=1,
        )


@pytest.mark.asyncio
async def test_recipient_verification_finishes_before_opening_operation_session() -> None:
    from inframeld_backend.access.application.errors.stranded_authority_maintenance_error import (
        StrandedAuthorityMaintenanceError,
    )

    events: list[str] = []

    @asynccontextmanager
    async def open_repair() -> AsyncGenerator[StrandedAuthorityRepairer]:
        events.append("open-session")
        try:
            yield MockRepairOperation(events)
        finally:
            events.append("close-session")

    command = RepairStrandedAuthorityCommand(
        expected_installation_id=InstallationId(UUID(int=4)),
        operation_id=OperationId("original"),
        responsibility=ActionGrantorRepairResponsibilityDTO(
            ProjectGrantTargetDTO(ProjectId(UUID(int=3))), ActionId("edit-project-metadata")
        ),
        expected_access_revision=0,
        expected_identity_id=UUID(int=5),
        operator_label="Operator",
        reason="Repair",
        identity_proof=HumanAccessTokenCredential("private-proof"),
    )
    result = await StrandedAuthorityMaintenanceCli(
        MockProofAuthenticator(events), open_repair
    ).execute(command)
    assert result["outcome"] == "repaired"
    assert events == ["verify-proof", "open-session", "repair", "close-session"]
    events.clear()
    with pytest.raises(StrandedAuthorityMaintenanceError):
        await StrandedAuthorityMaintenanceCli(
            MockProofAuthenticator(events, reject=True), open_repair
        ).execute(command)
    assert events == ["verify-proof"]


def test_mode_dispatch_preserves_the_existing_recovery_command() -> None:
    request = {
        "schemaVersion": 1,
        "mode": "resume-recovery-cleanup",
        "expectedInstallationId": str(UUID(int=4)),
        "operationId": "host-original",
        "recoveryOperationId": "recovery-original",
        "operatorLabel": "Operator",
        "reason": "Continue",
    }
    command = MaintenanceCli.read(io.BytesIO(json.dumps(request).encode()))
    assert command.operation_id.value == "host-original"


@pytest.mark.parametrize(
    ("intent", "attribution"),
    [
        (HumanSuspensionCleanupMaintenanceIntent.INSPECT, {}),
        (
            HumanSuspensionCleanupMaintenanceIntent.CONTINUE,
            {"operatorLabel": "Operator", "reason": "Continue stopped original"},
        ),
    ],
    ids=["inspect", "continue"],
)
def test_mode_dispatch_accepts_the_two_suspension_cleanup_intents(
    intent: HumanSuspensionCleanupMaintenanceIntent, attribution: dict[str, str]
) -> None:
    request = {
        "schemaVersion": 1,
        "mode": "human-suspension-cleanup",
        "intent": intent.value,
        "expectedInstallationId": str(UUID(int=4)),
        "operationId": "host-request",
        "cleanupOperationId": "retained-original",
        **attribution,
    }

    command = MaintenanceCli.read(io.BytesIO(json.dumps(request).encode()))

    assert isinstance(command, HumanSuspensionCleanupMaintenanceCommand)
    assert command.intent is intent
    assert command.expected_installation_id == InstallationId(UUID(int=4))
    assert command.operation_id == OperationId("host-request")
    assert command.cleanup_operation_id == OperationId("retained-original")
    assert command.operator_label == attribution.get("operatorLabel")
    assert command.reason == attribution.get("reason")


@pytest.mark.parametrize(
    "changes",
    [
        {"schemaVersion": True},
        {"schemaVersion": 1.0},
        {"intent": "retry"},
        {"operatorLabel": "Operator", "reason": "Inspect"},
        {"intent": "continue", "operatorLabel": "Operator"},
        {"intent": "continue", "reason": "Continue"},
        {"intent": "continue", "operatorLabel": " ", "reason": "Continue"},
        {"intent": "continue", "operatorLabel": "Operator", "reason": "r" * 513},
        {"identityProof": {"kind": "unexpected"}},
    ],
)
def test_suspension_cleanup_rejects_invalid_intent_or_fields(changes: dict[str, object]) -> None:
    request: dict[str, object] = {
        "schemaVersion": 1,
        "mode": "human-suspension-cleanup",
        "intent": "inspect",
        "expectedInstallationId": str(UUID(int=4)),
        "operationId": "host-request",
        "cleanupOperationId": "retained-original",
    }
    request.update(changes)

    with pytest.raises(StrandedAuthorityMaintenanceInputError) as error:
        MaintenanceCli.read(io.BytesIO(json.dumps(request).encode()))

    assert error.value.operation_id == OperationId("host-request")


def test_suspension_cleanup_requires_one_bounded_json_value() -> None:
    payload = json.dumps(
        {
            "schemaVersion": 1,
            "mode": "human-suspension-cleanup",
            "intent": "inspect",
            "expectedInstallationId": str(UUID(int=4)),
            "operationId": "host-request",
            "cleanupOperationId": "retained-original",
        }
    ).encode()
    bounded = payload.ljust(65_536, b" ")
    assert isinstance(
        MaintenanceCli.read(io.BytesIO(bounded)), HumanSuspensionCleanupMaintenanceCommand
    )
    for invalid in (
        bounded + b" ",
        payload + b" {}",
        payload[:-1] + b', "intent": "inspect"}',
    ):
        with pytest.raises(StrandedAuthorityMaintenanceInputError):
            MaintenanceCli.read(io.BytesIO(invalid))


def test_mode_dispatch_accepts_the_fixed_first_administrator_claim() -> None:
    request = {
        "schemaVersion": 1,
        "mode": "bootstrap-first-administrator",
        "expectedInstallationId": str(UUID(int=4)),
        "operationId": "first-claim",
        "operatorLabel": "Operator",
        "reason": "Establish first admission",
        "expectedAccessRevision": 0,
        "expectedIdentityId": str(UUID(int=5)),
        "identityProof": {"kind": "hydra-access-token", "accessToken": "private-proof"},
    }

    command = MaintenanceCli.read(io.BytesIO(json.dumps(request).encode()))

    assert isinstance(command, BootstrapFirstAdministratorCommand)
    assert command.operation_id == OperationId("first-claim")
    assert command.expected_identity_id == UUID(int=5)
    assert command.expected_access_revision == 0


@pytest.mark.parametrize(
    "responsibility",
    [
        {
            "kind": "group-manager",
            "projectId": "00000000-0000-0000-0000-000000000003",
            "accessGroupId": "00000000-0000-0000-0000-000000000009",
        },
        {
            "kind": "action-grantor",
            "target": {
                "kind": "organization",
                "organizationId": "00000000-0000-0000-0000-000000000002",
            },
            "actionId": "admit-users",
        },
        {
            "kind": "action-grantor",
            "target": {"kind": "project", "projectId": "00000000-0000-0000-0000-000000000003"},
            "actionId": "manage-project-members",
        },
        {
            "kind": "action-grantor",
            "target": {
                "kind": "access-group",
                "projectId": "00000000-0000-0000-0000-000000000003",
                "accessGroupId": "00000000-0000-0000-0000-000000000009",
            },
            "actionId": "add-documents",
        },
        {
            "kind": "action-grantor",
            "target": {
                "kind": "application-account",
                "projectId": "00000000-0000-0000-0000-000000000003",
                "applicationPrincipalId": "00000000-0000-0000-0000-000000000008",
            },
            "actionId": "revoke-application-keys",
        },
        {
            "kind": "action-grantor",
            "target": {
                "kind": "model-connection",
                "projectId": "00000000-0000-0000-0000-000000000003",
                "modelConnectionId": "00000000-0000-0000-0000-00000000000a",
            },
            "actionId": "use-model-connection",
        },
    ],
)
def test_private_dispatch_accepts_each_delivered_access_responsibility(
    responsibility: dict[str, object],
) -> None:
    request = {
        "schemaVersion": 1,
        "mode": "repair-stranded-authority",
        "expectedInstallationId": str(UUID(int=4)),
        "operationId": "dispatch-original",
        "operatorLabel": "Host operator",
        "reason": "Repair exact reviewed Access responsibility",
        "expectedAccessRevision": 0,
        "expectedIdentityId": str(UUID(int=5)),
        "identityProof": {"kind": "hydra-access-token", "accessToken": "private-proof"},
        "responsibility": responsibility,
    }
    command = MaintenanceCli.read(io.BytesIO(json.dumps(request).encode()))
    assert isinstance(command, RepairStrandedAuthorityCommand)
    assert command.responsibility.kind.value == responsibility["kind"]
    assert command.operation_id.value == "dispatch-original"
    assert "private-proof" not in repr(command)
