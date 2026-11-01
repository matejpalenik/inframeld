import io
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import override
from uuid import UUID

import pytest

from inframeld_backend.access.application.commands.repair_project_metadata_authority_command import (
    RepairProjectMetadataAuthorityCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.project_metadata_repair_result_dto import (
    ProjectMetadataRepairResultDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.human_access_token_authenticator import (
    HumanAccessTokenAuthenticator,
)
from inframeld_backend.access.application.protocols.project_metadata_repairer import (
    ProjectMetadataRepairer,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.cli.maintenance_cli import MaintenanceCli
from inframeld_backend.access.cli.project_metadata_maintenance_cli import (
    ProjectMetadataMaintenanceCli,
)
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


class MockRepairOperation(ProjectMetadataRepairer):
    def __init__(self, events: list[str]) -> None:
        self.events = events

    @override
    async def repair(
        self, *, access: AccessContextDTO, command: RepairProjectMetadataAuthorityCommand
    ) -> ProjectMetadataRepairResultDTO:
        self.events.append("repair")
        return ProjectMetadataRepairResultDTO(
            command.operation_id,
            command.expected_installation_id,
            OrganizationId(UUID(int=2)),
            command.project_id,
            access.actor_principal_id,
            1,
        )


@pytest.mark.asyncio
async def test_recipient_verification_finishes_before_opening_operation_session() -> None:
    from inframeld_backend.access.application.errors.project_metadata_maintenance_error import (
        ProjectMetadataMaintenanceError,
    )

    events: list[str] = []

    @asynccontextmanager
    async def open_repair() -> AsyncGenerator[ProjectMetadataRepairer]:
        events.append("open-session")
        try:
            yield MockRepairOperation(events)
        finally:
            events.append("close-session")

    command = RepairProjectMetadataAuthorityCommand(
        InstallationId(UUID(int=4)),
        OperationId("original"),
        ProjectId(UUID(int=3)),
        0,
        UUID(int=5),
        "Operator",
        "Repair",
        HumanAccessTokenCredential("private-proof"),
    )
    result = await ProjectMetadataMaintenanceCli(
        MockProofAuthenticator(events), open_repair
    ).execute(command)
    assert result["outcome"] == "repaired"
    assert events == ["verify-proof", "open-session", "repair", "close-session"]
    events.clear()
    with pytest.raises(ProjectMetadataMaintenanceError):
        await ProjectMetadataMaintenanceCli(
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
