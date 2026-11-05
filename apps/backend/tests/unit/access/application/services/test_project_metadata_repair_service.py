from dataclasses import replace
from datetime import UTC, datetime
from typing import override
from uuid import UUID

import pytest
from tests.support.mock_project_metadata import MockTransactions

from inframeld_backend.access.application.commands.repair_project_metadata_authority_command import (
    RepairProjectMetadataAuthorityCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_facts_dto import (
    HumanOAuthCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.project_metadata_repair_facts_dto import (
    ProjectMetadataRepairFactsDTO,
)
from inframeld_backend.access.application.dtos.project_metadata_repair_receipt_dto import (
    ProjectMetadataRepairReceiptDTO,
)
from inframeld_backend.access.application.dtos.project_metadata_repair_result_dto import (
    ProjectMetadataRepairResultDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.project_metadata_maintenance_error_code import (
    ProjectMetadataMaintenanceErrorCode as Code,
)
from inframeld_backend.access.application.errors.project_metadata_maintenance_error import (
    ProjectMetadataMaintenanceError,
)
from inframeld_backend.access.application.protocols.project_metadata_repair_facts_reader import (
    ProjectMetadataRepairFactsReader,
)
from inframeld_backend.access.application.protocols.project_metadata_repair_writer import (
    ProjectMetadataRepairWriter,
)
from inframeld_backend.access.application.services.project_metadata_fingerprint_service import (
    ProjectMetadataFingerprintService,
)
from inframeld_backend.access.application.services.project_metadata_repair_service import (
    ProjectMetadataRepairService,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

IDENTITY = VerifiedHumanIdentityDTO(
    IdentityAuthority("kratos:test"), IdentitySubject(str(UUID(int=5)))
)
INSTALLATION = InstallationId(UUID(int=4))
ACTOR = Principal(
    PrincipalId(UUID(int=1)),
    OrganizationId(UUID(int=2)),
    PrincipalKind.HUMAN,
    PrincipalStatus.ACTIVE,
)
PROJECT = ProjectId(UUID(int=3))
ACCESS = AccessContextDTO(
    ACTOR.id, HumanOAuthCredentialBindingDTO(IDENTITY, INSTALLATION, HumanCredentialVersion(2))
)
COMMAND = RepairProjectMetadataAuthorityCommand(
    expected_installation_id=INSTALLATION,
    operation_id=OperationId("operator-original"),
    project_id=PROJECT,
    expected_access_revision=0,
    expected_identity_id=UUID(int=5),
    operator_label="Operator",
    reason="Repair metadata authority",
    identity_proof=HumanAccessTokenCredential("first-proof"),
)


class MockRepairFacts(ProjectMetadataRepairFactsReader):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.facts = ProjectMetadataRepairFactsDTO(
            installation_id=INSTALLATION,
            recipient=ACTOR,
            project_id=PROJECT,
            project_status=ProjectStatus.ACTIVE,
            access_revision=0,
            is_project_member=True,
            has_pending_recovery=False,
            oauth_credential_facts=HumanOAuthCredentialFactsDTO(True, HumanCredentialVersion(2)),
            eligible_grantor_exists=False,
            observed_at=datetime(2030, 1, 1, tzinfo=UTC),
        )
        self.saved: ProjectMetadataRepairReceiptDTO | None = None

    @override
    async def read(
        self, *, access: AccessContextDTO, command: RepairProjectMetadataAuthorityCommand
    ) -> ProjectMetadataRepairFactsDTO | None:
        self.events.append("facts")
        return self.facts

    @override
    async def receipt(
        self, *, installation_id: InstallationId, operation_id: OperationId
    ) -> ProjectMetadataRepairReceiptDTO | None:
        self.events.append("receipt")
        return self.saved


class MockRepairWriter(ProjectMetadataRepairWriter):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.recorded: ProjectMetadataRepairReceiptDTO | None = None

    @override
    async def record(self, receipt: ProjectMetadataRepairReceiptDTO) -> bool:
        self.events.append("record")
        self.recorded = receipt
        return True

    @override
    async def assign(
        self, *, facts: ProjectMetadataRepairFactsDTO, receipt: ProjectMetadataRepairReceiptDTO
    ) -> None:
        self.events.append("assign")


class Scenario:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.facts = MockRepairFacts(self.events)
        self.writer = MockRepairWriter(self.events)
        self.fingerprints = ProjectMetadataFingerprintService(
            RequestFingerprintService(RequestFingerprintKey(b"K" * 32))
        )
        self.service = ProjectMetadataRepairService(
            transaction_manager=MockTransactions(self.events),
            metadata_repair_facts_reader=self.facts,
            metadata_repair_writer=self.writer,
            metadata_fingerprint_service=self.fingerprints,
        )

    def save_original(self) -> None:
        result = ProjectMetadataRepairResultDTO(
            operation_id=COMMAND.operation_id,
            installation_id=INSTALLATION,
            organization_id=ACTOR.organization_id,
            project_id=PROJECT,
            recipient_id=ACTOR.id,
            access_revision=1,
        )
        self.facts.saved = ProjectMetadataRepairReceiptDTO(
            fingerprint=self.fingerprints.for_repair(COMMAND, IDENTITY),
            identity=IDENTITY,
            expected_identity_id=COMMAND.expected_identity_id,
            operator_label=COMMAND.operator_label,
            reason=COMMAND.reason,
            before_revision=0,
            authorized_at=self.facts.facts.observed_at,
            result=result,
        )


@pytest.mark.asyncio
async def test_new_repair_records_exact_outcome_before_assignment_in_same_transaction() -> None:
    s = Scenario()
    result = await s.service.repair(access=ACCESS, command=COMMAND)
    assert result.access_revision == 1 and result.recipient_id == ACTOR.id
    assert s.events == ["begin", "facts", "receipt", "record", "assign", "commit"]
    assert s.writer.recorded is not None
    assert "first-proof" not in repr(s.writer.recorded)


@pytest.mark.asyncio
@pytest.mark.parametrize("revision", [20, 2**53 - 1])
async def test_current_refreshed_proof_replays_before_new_revision_or_stranded_checks_without_regrant(
    revision: int,
) -> None:
    s = Scenario()
    s.save_original()
    s.facts.facts = replace(s.facts.facts, access_revision=revision, eligible_grantor_exists=True)
    result = await s.service.repair(
        access=ACCESS,
        command=replace(COMMAND, identity_proof=HumanAccessTokenCredential("refreshed-proof")),
    )
    assert result.access_revision == 1
    assert s.events == ["begin", "facts", "receipt", "commit"]


@pytest.mark.asyncio
async def test_provider_active_old_generation_proof_is_rejected_before_completed_receipt_lookup() -> (
    None
):
    s = Scenario()
    s.save_original()
    s.facts.facts = replace(
        s.facts.facts,
        oauth_credential_facts=HumanOAuthCredentialFactsDTO(True, HumanCredentialVersion(3)),
    )
    with pytest.raises(ProjectMetadataMaintenanceError) as failure:
        await s.service.repair(access=ACCESS, command=COMMAND)
    assert failure.value.code is Code.INVALID_IDENTITY_PROOF
    assert "receipt" not in s.events and "assign" not in s.events


@pytest.mark.asyncio
async def test_changed_original_meaning_conflicts_and_unavailable_stranded_facts_cannot_assign() -> (
    None
):
    s = Scenario()
    s.save_original()
    with pytest.raises(ProjectMetadataMaintenanceError) as failure:
        await s.service.repair(
            access=ACCESS, command=replace(COMMAND, reason="Different reviewed purpose")
        )
    assert failure.value.code is Code.KEY_REUSED
    s.facts.saved = None
    s.facts.facts = replace(s.facts.facts, eligible_grantor_exists=None)
    with pytest.raises(ProjectMetadataMaintenanceError) as failure:
        await s.service.repair(access=ACCESS, command=COMMAND)
    assert failure.value.code is Code.DEPENDENCY_UNAVAILABLE
    assert "assign" not in s.events


@pytest.mark.asyncio
async def test_exhausted_repair_revision_rejects_fresh_authorized_change_before_receipt_effects() -> (
    None
):
    scenario = Scenario()
    scenario.facts.facts = replace(scenario.facts.facts, access_revision=2**53 - 1)
    command = replace(COMMAND, expected_access_revision=2**53 - 1)

    with pytest.raises(ProjectMetadataMaintenanceError) as failure:
        await scenario.service.repair(access=ACCESS, command=command)

    assert failure.value.code is Code.REVISION_EXHAUSTED
    assert scenario.writer.recorded is None and scenario.facts.saved is None
    assert scenario.events == ["begin", "facts", "receipt", "rollback"]
