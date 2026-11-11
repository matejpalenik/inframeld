from dataclasses import replace
from datetime import UTC, datetime
from typing import override
from uuid import UUID

import pytest
from tests.support.mock_project_metadata import MockTransactions

from inframeld_backend.access.application.commands.repair_stranded_authority_command import (
    RepairStrandedAuthorityCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
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
from inframeld_backend.access.application.dtos.human_credential_facts_dto import (
    HumanCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.organization_grant_target_dto import (
    OrganizationGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.project_grant_target_dto import ProjectGrantTargetDTO
from inframeld_backend.access.application.dtos.stranded_authority_repair_facts_dto import (
    StrandedAuthorityRepairFactsDTO,
)
from inframeld_backend.access.application.dtos.stranded_authority_repair_receipt_dto import (
    StrandedAuthorityRepairReceiptDTO,
)
from inframeld_backend.access.application.dtos.stranded_authority_repair_result_dto import (
    StrandedAuthorityRepairResultDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.stranded_authority_maintenance_error_code import (
    StrandedAuthorityMaintenanceErrorCode,
)
from inframeld_backend.access.application.enums.stranded_authority_maintenance_error_code import (
    StrandedAuthorityMaintenanceErrorCode as Code,
)
from inframeld_backend.access.application.errors.stranded_authority_maintenance_error import (
    StrandedAuthorityMaintenanceError,
)
from inframeld_backend.access.application.protocols.stranded_authority_repair_facts_reader import (
    StrandedAuthorityRepairFactsReader,
)
from inframeld_backend.access.application.protocols.stranded_authority_repair_writer import (
    StrandedAuthorityRepairWriter,
)
from inframeld_backend.access.application.services.stranded_authority_fingerprint_service import (
    StrandedAuthorityFingerprintService,
)
from inframeld_backend.access.application.services.stranded_authority_repair_service import (
    StrandedAuthorityRepairService,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.action_id import ActionId
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
COMMAND = RepairStrandedAuthorityCommand(
    expected_installation_id=INSTALLATION,
    operation_id=OperationId("operator-original"),
    responsibility=ActionGrantorRepairResponsibilityDTO(
        ProjectGrantTargetDTO(PROJECT), ActionId("edit-project-metadata")
    ),
    expected_access_revision=0,
    expected_identity_id=UUID(int=5),
    operator_label="Operator",
    reason="Repair metadata authority",
    identity_proof=HumanAccessTokenCredential("first-proof"),
)


class MockRepairFacts(StrandedAuthorityRepairFactsReader):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.facts = StrandedAuthorityRepairFactsDTO(
            installation_id=INSTALLATION,
            recipient=ACTOR,
            responsibility=ActionGrantorRepairResponsibilityDTO(
                ProjectGrantTargetDTO(PROJECT), ActionId("edit-project-metadata")
            ),
            project_status=ProjectStatus.ACTIVE,
            access_revision=0,
            is_project_member=True,
            has_pending_recovery=False,
            oauth_credential_facts=HumanCredentialFactsDTO(True, HumanCredentialVersion(2)),
            eligible_grantor_exists=False,
            target_exists=True,
            target_accepts_assignment=True,
            observed_at=datetime(2030, 1, 1, tzinfo=UTC),
        )
        self.saved: StrandedAuthorityRepairReceiptDTO | None = None

    @override
    async def read(
        self, *, access: AccessContextDTO, command: RepairStrandedAuthorityCommand
    ) -> StrandedAuthorityRepairFactsDTO | None:
        self.events.append("facts")
        return self.facts

    @override
    async def receipt(
        self, *, installation_id: InstallationId, operation_id: OperationId
    ) -> StrandedAuthorityRepairReceiptDTO | None:
        self.events.append("receipt")
        return self.saved


class MockRepairWriter(StrandedAuthorityRepairWriter):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.recorded: StrandedAuthorityRepairReceiptDTO | None = None

    @override
    async def record(self, receipt: StrandedAuthorityRepairReceiptDTO) -> bool:
        self.events.append("record")
        self.recorded = receipt
        return True

    @override
    async def assign(
        self, *, facts: StrandedAuthorityRepairFactsDTO, receipt: StrandedAuthorityRepairReceiptDTO
    ) -> None:
        self.events.append("assign")


class Scenario:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.facts = MockRepairFacts(self.events)
        self.writer = MockRepairWriter(self.events)
        self.fingerprints = StrandedAuthorityFingerprintService(
            RequestFingerprintService(RequestFingerprintKey(b"K" * 32))
        )
        self.service = StrandedAuthorityRepairService(
            transaction_manager=MockTransactions(self.events),
            repair_facts_reader=self.facts,
            repair_writer=self.writer,
            repair_fingerprint_service=self.fingerprints,
        )

    def save_original(self) -> None:
        result = StrandedAuthorityRepairResultDTO(
            operation_id=COMMAND.operation_id,
            installation_id=INSTALLATION,
            organization_id=ACTOR.organization_id,
            responsibility=ActionGrantorRepairResponsibilityDTO(
                ProjectGrantTargetDTO(PROJECT), ActionId("edit-project-metadata")
            ),
            recipient_id=ACTOR.id,
            access_revision=1,
        )
        self.facts.saved = StrandedAuthorityRepairReceiptDTO(
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
        oauth_credential_facts=HumanCredentialFactsDTO(True, HumanCredentialVersion(3)),
    )
    with pytest.raises(StrandedAuthorityMaintenanceError) as failure:
        await s.service.repair(access=ACCESS, command=COMMAND)
    assert failure.value.code is Code.INVALID_IDENTITY_PROOF
    assert "receipt" not in s.events and "assign" not in s.events


@pytest.mark.asyncio
async def test_changed_original_meaning_conflicts_and_unavailable_stranded_facts_cannot_assign() -> (
    None
):
    s = Scenario()
    s.save_original()
    with pytest.raises(StrandedAuthorityMaintenanceError) as failure:
        await s.service.repair(
            access=ACCESS, command=replace(COMMAND, reason="Different reviewed purpose")
        )
    assert failure.value.code is Code.KEY_REUSED
    s.facts.saved = None
    s.facts.facts = replace(s.facts.facts, eligible_grantor_exists=None)
    with pytest.raises(StrandedAuthorityMaintenanceError) as failure:
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

    with pytest.raises(StrandedAuthorityMaintenanceError) as failure:
        await scenario.service.repair(access=ACCESS, command=command)

    assert failure.value.code is Code.REVISION_EXHAUSTED
    assert scenario.writer.recorded is None and scenario.facts.saved is None
    assert scenario.events == ["begin", "facts", "receipt", "rollback"]


RESPONSIBILITIES = [
    GroupManagerRepairResponsibilityDTO(PROJECT, AccessGroupId(UUID(int=9))),
    ActionGrantorRepairResponsibilityDTO(
        OrganizationGrantTargetDTO(ACTOR.organization_id), ActionId("admit-users")
    ),
    ActionGrantorRepairResponsibilityDTO(
        ProjectGrantTargetDTO(PROJECT), ActionId("edit-project-metadata")
    ),
    ActionGrantorRepairResponsibilityDTO(
        AccessGroupGrantTargetDTO(PROJECT, AccessGroupId(UUID(int=9))), ActionId("add-documents")
    ),
    ActionGrantorRepairResponsibilityDTO(
        ApplicationAccountGrantTargetDTO(PROJECT, PrincipalId(UUID(int=8))),
        ActionId("revoke-application-keys"),
    ),
]


class BroaderFacts(StrandedAuthorityRepairFactsReader):
    def __init__(self, events: list[str], command: RepairStrandedAuthorityCommand) -> None:
        self.events = events
        organization_only = isinstance(
            command.responsibility, ActionGrantorRepairResponsibilityDTO
        ) and isinstance(command.responsibility.target, OrganizationGrantTargetDTO)
        self.facts = StrandedAuthorityRepairFactsDTO(
            INSTALLATION,
            ACTOR,
            command.responsibility,
            None if organization_only else ProjectStatus.ACTIVE,
            0,
            not organization_only,
            False,
            HumanCredentialFactsDTO(True, HumanCredentialVersion(2)),
            False,
            True,
            True,
            datetime(2030, 1, 1, tzinfo=UTC),
        )
        self.saved: StrandedAuthorityRepairReceiptDTO | None = None

    @override
    async def read(
        self, *, access: AccessContextDTO, command: RepairStrandedAuthorityCommand
    ) -> StrandedAuthorityRepairFactsDTO | None:
        self.events.append("facts")
        return self.facts

    @override
    async def receipt(
        self, *, installation_id: InstallationId, operation_id: OperationId
    ) -> StrandedAuthorityRepairReceiptDTO | None:
        self.events.append("receipt")
        return self.saved


class BroaderWriter(StrandedAuthorityRepairWriter):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.recorded: StrandedAuthorityRepairReceiptDTO | None = None
        self.error: Exception | None = None

    @override
    async def record(self, receipt: StrandedAuthorityRepairReceiptDTO) -> bool:
        self.events.append("record")
        self.recorded = receipt
        return True

    @override
    async def assign(
        self, *, facts: StrandedAuthorityRepairFactsDTO, receipt: StrandedAuthorityRepairReceiptDTO
    ) -> None:
        self.events.append("assign")
        if self.error is not None:
            raise self.error


class BroaderScenario:
    def __init__(
        self,
        responsibility: GroupManagerRepairResponsibilityDTO | ActionGrantorRepairResponsibilityDTO,
    ) -> None:
        self.events: list[str] = []
        self.command = RepairStrandedAuthorityCommand(
            INSTALLATION,
            COMMAND.operation_id,
            responsibility,
            0,
            COMMAND.expected_identity_id,
            COMMAND.operator_label,
            COMMAND.reason,
            COMMAND.identity_proof,
        )
        self.facts = BroaderFacts(self.events, self.command)
        self.writer = BroaderWriter(self.events)
        self.fingerprints = StrandedAuthorityFingerprintService(
            RequestFingerprintService(RequestFingerprintKey(b"K" * 32))
        )
        self.service = StrandedAuthorityRepairService(
            transaction_manager=MockTransactions(self.events),
            repair_facts_reader=self.facts,
            repair_writer=self.writer,
            repair_fingerprint_service=self.fingerprints,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("responsibility", RESPONSIBILITIES)
async def test_broader_repair_saves_only_exact_responsibility_in_one_transaction(
    responsibility: GroupManagerRepairResponsibilityDTO | ActionGrantorRepairResponsibilityDTO,
) -> None:
    s = BroaderScenario(responsibility)
    result = await s.service.repair(access=ACCESS, command=s.command)
    assert result.responsibility == responsibility
    assert result.recipient_id == ACTOR.id and result.access_revision == 1
    assert s.events == ["begin", "facts", "receipt", "record", "assign", "commit"]
    assert s.writer.recorded is not None and "first-proof" not in repr(s.writer.recorded)


@pytest.mark.asyncio
@pytest.mark.parametrize("responsibility", RESPONSIBILITIES)
async def test_broader_completed_original_precedes_fresh_revision_and_stranded_checks_without_regrant(
    responsibility: GroupManagerRepairResponsibilityDTO | ActionGrantorRepairResponsibilityDTO,
) -> None:
    s = BroaderScenario(responsibility)
    original = await s.service.repair(access=ACCESS, command=s.command)
    s.facts.saved = s.writer.recorded
    s.facts.facts = replace(s.facts.facts, access_revision=25, eligible_grantor_exists=True)
    s.events.clear()
    replay = await s.service.repair(
        access=ACCESS,
        command=replace(s.command, identity_proof=HumanAccessTokenCredential("refreshed-proof")),
    )
    assert replay == original
    assert s.events == ["begin", "facts", "receipt", "commit"]


@pytest.mark.asyncio
@pytest.mark.parametrize("loss", ["credential", "recovery", "membership", "target"])
async def test_broader_current_eligibility_and_scope_precede_original_recovery(loss: str) -> None:
    s = BroaderScenario(RESPONSIBILITIES[0])
    await s.service.repair(access=ACCESS, command=s.command)
    s.facts.saved = s.writer.recorded
    if loss == "credential":
        s.facts.facts = replace(
            s.facts.facts,
            oauth_credential_facts=HumanCredentialFactsDTO(True, HumanCredentialVersion(3)),
        )
    elif loss == "recovery":
        s.facts.facts = replace(s.facts.facts, has_pending_recovery=True)
    elif loss == "membership":
        s.facts.facts = replace(s.facts.facts, is_project_member=False)
    else:
        s.facts.facts = replace(s.facts.facts, target_exists=False)
    s.events.clear()
    with pytest.raises(StrandedAuthorityMaintenanceError) as failure:
        await s.service.repair(access=ACCESS, command=s.command)
    expected = (
        StrandedAuthorityMaintenanceErrorCode.INVALID_IDENTITY_PROOF
        if loss == "credential"
        else StrandedAuthorityMaintenanceErrorCode.IDENTITY_INELIGIBLE
    )
    assert failure.value.code is expected
    assert s.events == ["begin", "facts", "rollback"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "grantor,code",
    [
        (True, StrandedAuthorityMaintenanceErrorCode.NOT_STRANDED),
        (None, StrandedAuthorityMaintenanceErrorCode.DEPENDENCY_UNAVAILABLE),
    ],
)
async def test_broader_existing_grantor_or_unknown_observation_never_assigns(
    grantor: bool | None, code: StrandedAuthorityMaintenanceErrorCode
) -> None:
    s = BroaderScenario(RESPONSIBILITIES[0])
    s.facts.facts = replace(s.facts.facts, eligible_grantor_exists=grantor)
    with pytest.raises(StrandedAuthorityMaintenanceError) as failure:
        await s.service.repair(access=ACCESS, command=s.command)
    assert failure.value.code is code
    assert s.writer.recorded is None
    assert s.events == ["begin", "facts", "receipt", "rollback"]


@pytest.mark.asyncio
async def test_broader_changed_original_meaning_conflicts_and_assignment_failure_rolls_back() -> (
    None
):
    s = BroaderScenario(RESPONSIBILITIES[0])
    await s.service.repair(access=ACCESS, command=s.command)
    s.facts.saved = s.writer.recorded
    with pytest.raises(StrandedAuthorityMaintenanceError) as failure:
        await s.service.repair(access=ACCESS, command=replace(s.command, reason="Changed meaning"))
    assert failure.value.code is StrandedAuthorityMaintenanceErrorCode.KEY_REUSED
    s.facts.saved = None
    s.writer.error = RuntimeError("audit failed")
    s.events.clear()
    with pytest.raises(RuntimeError, match="audit failed"):
        await s.service.repair(access=ACCESS, command=s.command)
    assert s.events == ["begin", "facts", "receipt", "record", "assign", "rollback"]


def test_broader_metadata_fingerprint_preserves_legacy_bytes_and_proof_refresh() -> None:
    s = BroaderScenario(RESPONSIBILITIES[2])
    actual = s.fingerprints.for_repair(s.command, IDENTITY)
    assert actual.value.hex() == "6a413475be407e3c14f32de90d00dd1adaee34950d1510e73c5c522f2dfa5557"
    assert (
        s.fingerprints.for_repair(
            replace(s.command, identity_proof=HumanAccessTokenCredential("other-proof")), IDENTITY
        )
        == actual
    )


def test_broader_fingerprint_binds_exact_kind_target_action_and_review_without_secret() -> None:
    s = BroaderScenario(RESPONSIBILITIES[0])
    fingerprints = {
        s.fingerprints.for_repair(replace(s.command, responsibility=r), IDENTITY)
        for r in RESPONSIBILITIES
    }
    assert len(fingerprints) == len(RESPONSIBILITIES)
    original = s.fingerprints.for_repair(s.command, IDENTITY)
    assert (
        s.fingerprints.for_repair(replace(s.command, expected_access_revision=1), IDENTITY)
        != original
    )
