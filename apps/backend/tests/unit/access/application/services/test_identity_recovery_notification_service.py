import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import override
from uuid import UUID

import pytest

from inframeld_backend.access.application.dtos.identity_recovery_admission_dto import (
    IdentityRecoveryAdmissionDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_association_facts_dto import (
    IdentityRecoveryAssociationFactsDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_event_dto import (
    IdentityRecoveryEventDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_session_binding_dto import (
    IdentityRecoverySessionBindingDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_settings_binding_dto import (
    IdentityRecoverySettingsBindingDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_settings_evidence_dto import (
    IdentityRecoverySettingsEvidenceDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.identity_recovery_event_kind import (
    IdentityRecoveryEventKind,
)
from inframeld_backend.access.application.protocols.identity_recovery_admitter import (
    IdentityRecoveryAdmitter,
)
from inframeld_backend.access.application.protocols.identity_recovery_association_facts_reader import (
    IdentityRecoveryAssociationFactsReader,
)
from inframeld_backend.access.application.protocols.identity_recovery_evidence_writer import (
    IdentityRecoveryEvidenceWriter,
)
from inframeld_backend.access.application.protocols.identity_recovery_repository import (
    IdentityRecoveryRepository,
)
from inframeld_backend.access.application.services.identity_recovery_notification_service import (
    IdentityRecoveryNotificationService,
)
from inframeld_backend.access.application.value_objects.identity_recovery_cleanup_run_budget import (
    IdentityRecoveryCleanupRunBudget,
)
from inframeld_backend.access.application.value_objects.identity_session_id import IdentitySessionId
from inframeld_backend.access.application.value_objects.identity_settings_flow_id import (
    IdentitySettingsFlowId,
)
from inframeld_backend.access.domain.entities.identity_recovery import IdentityRecovery
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState as State,
)
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_recovery_flow_id import (
    IdentityRecoveryFlowId,
)
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

INSTALLATION = InstallationId(UUID(int=1))
EVENT = IdentityRecoveryEventDTO(
    IdentityRecoveryFlowId(UUID(int=2)),
    VerifiedHumanIdentityDTO(
        IdentityAuthority("https://identity.test"), IdentitySubject(str(UUID(int=3)))
    ),
    IdentityRecoveryEventKind.RECOVERY,
)
OPERATION = OperationId("original-recovery")
EVIDENCE = IdentityRecoverySettingsEvidenceDTO(
    EVENT.identity,
    IdentitySettingsFlowId(UUID(int=4)),
    IdentitySessionId(UUID(int=5)),
    EVENT.flow_id,
)


ADMISSION = IdentityRecoveryAdmissionDTO(EVENT, OPERATION)
RECORDED_AT = datetime(2026, 10, 26, 12, tzinfo=UTC)
SESSION_BINDING = IdentityRecoverySessionBindingDTO(EVENT.identity, EVIDENCE.session_id, OPERATION)
SETTINGS_BINDING = IdentityRecoverySettingsBindingDTO(
    EVENT.identity, EVIDENCE.settings_flow_id, EVIDENCE.session_id, OPERATION, EVENT.flow_id
)
FACTS = IdentityRecoveryAssociationFactsDTO(
    ADMISSION, SESSION_BINDING, ADMISSION, SETTINGS_BINDING, ADMISSION, HumanCredentialVersion(2)
)
EMPTY_FACTS = IdentityRecoveryAssociationFactsDTO(None, None, None, None, None, None)


class Scenario(
    TransactionManager,
    IdentityRecoveryAdmitter,
    IdentityRecoveryAssociationFactsReader,
    IdentityRecoveryEvidenceWriter,
    IdentityRecoveryRepository,
):
    def __init__(self) -> None:
        self.events: list[str] = []
        self.facts = FACTS
        self.read_evidence: IdentityRecoverySettingsEvidenceDTO | None = None
        self.written_admission: IdentityRecoveryAdmissionDTO | None = None
        self.budget: IdentityRecoveryCleanupRunBudget | None = None
        self.recorded_at = RECORDED_AT
        self.error: Exception | None = None
        self.receipt_error: Exception | None = None
        self.commit_gate: asyncio.Event | None = None
        self.commit_entered = asyncio.Event()
        self.recovery = IdentityRecovery(
            installation_id=INSTALLATION,
            authority=EVENT.identity.authority,
            flow_id=EVENT.flow_id,
            subject=EVENT.identity.subject,
        )
        self.service = IdentityRecoveryNotificationService(
            self, self, self, self, facts=self, installation_id=INSTALLATION
        )

    @override
    @asynccontextmanager
    async def begin(self) -> AsyncGenerator[None]:
        self.events.append("begin")
        try:
            yield
            self.commit_entered.set()
            if self.commit_gate is not None:
                await self.commit_gate.wait()
            self.events.append("commit")
        except BaseException:
            self.events.append("rollback")
            raise

    @override
    async def admit(self, event: IdentityRecoveryEventDTO) -> OperationId:
        assert event == EVENT
        self.events.append("admit")
        return OPERATION

    @override
    async def read(
        self, evidence: IdentityRecoverySettingsEvidenceDTO
    ) -> IdentityRecoveryAssociationFactsDTO:
        self.read_evidence = evidence
        self.events.append("read_facts")
        return self.facts

    @override
    async def record_admission(
        self, event: IdentityRecoveryEventDTO, operation_id: OperationId
    ) -> None:
        assert (event, operation_id) == (EVENT, OPERATION)
        self.events.append("receipt")

    @override
    async def record_settings_association(
        self, evidence: IdentityRecoverySettingsEvidenceDTO, admission: IdentityRecoveryAdmissionDTO
    ) -> None:
        assert evidence is self.read_evidence
        self.written_admission = admission
        self.events.append("associate")

    @override
    async def record_password_saved(
        self, evidence: IdentityRecoverySettingsEvidenceDTO, admission: IdentityRecoveryAdmissionDTO
    ) -> datetime:
        assert evidence is self.read_evidence
        self.written_admission = admission
        self.events.append("password_receipt")
        if self.receipt_error is not None:
            raise self.receipt_error
        return self.recorded_at

    @override
    async def ensure_initial_cleanup_handoff(
        self,
        evidence: IdentityRecoverySettingsEvidenceDTO,
        admission: IdentityRecoveryAdmissionDTO,
        *,
        budget: IdentityRecoveryCleanupRunBudget,
    ) -> None:
        assert evidence is self.read_evidence
        assert admission is self.written_admission
        self.budget = budget
        self.events.append("handoff")
        if self.error is not None:
            raise self.error

    @override
    async def get(
        self,
        *,
        installation_id: InstallationId,
        authority: IdentityAuthority,
        flow_id: IdentityRecoveryFlowId,
    ) -> IdentityRecovery:
        assert (installation_id, authority, flow_id) == (
            INSTALLATION,
            EVENT.identity.authority,
            EVENT.flow_id,
        )
        self.events.append("load")
        return self.recovery

    @override
    async def save(self, recovery: IdentityRecovery) -> None:
        assert recovery is self.recovery
        self.events.append("save")


@pytest.mark.asyncio
async def test_admission_acknowledges_only_after_commit() -> None:
    s = Scenario()
    result = await s.service.admit(EVENT)
    assert result.operation_id == OPERATION
    assert s.events == ["begin", "admit", "receipt", "commit"]


@pytest.mark.asyncio
async def test_password_evidence_confirms_only_kratos_and_saves_handoff_before_commit() -> None:
    s = Scenario()
    result = await s.service.record_password_saved(EVIDENCE)
    assert result is not None and result.operation_id == OPERATION
    assert s.events == [
        "begin",
        "read_facts",
        "load",
        "save",
        "password_receipt",
        "handoff",
        "commit",
    ]
    assert s.recovery.kratos_cleanup_state is State.CONFIRMED
    assert s.recovery.hydra_cleanup_state is State.PENDING
    assert not s.recovery.is_released


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["associate_settings", "record_password_saved"])
async def test_ordinary_settings_perform_no_recovery_work(operation: str) -> None:
    s = Scenario()
    s.facts = EMPTY_FACTS
    result = await getattr(s.service, operation)(replace(EVIDENCE, source_recovery_flow_id=None))
    assert result is None
    assert s.events == ["begin", "read_facts", "commit"]


@pytest.mark.asyncio
async def test_failed_handoff_rolls_back_and_returns_no_acknowledgment() -> None:
    s = Scenario()
    s.error = ConflictError()
    with pytest.raises(ConflictError):
        await s.service.record_password_saved(EVIDENCE)
    assert s.events[-1] == "rollback"
    assert "commit" not in s.events


@pytest.mark.asyncio
async def test_cancellation_during_transaction_exit_propagates_without_acknowledgment() -> None:
    s = Scenario()
    s.commit_gate = asyncio.Event()
    task = asyncio.create_task(s.service.admit(EVENT))
    await asyncio.wait_for(s.commit_entered.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert s.events[-1] == "rollback"


@pytest.mark.asyncio
async def test_database_deadline_includes_transaction_exit() -> None:
    s = Scenario()
    s.commit_gate = asyncio.Event()
    s.service = IdentityRecoveryNotificationService(
        s, s, s, s, facts=s, installation_id=INSTALLATION, database_timeout_seconds=0.02
    )
    with pytest.raises(DependencyUnavailableError):
        await s.service.admit(EVENT)
    assert s.events[-1] == "rollback"


@pytest.mark.asyncio
@pytest.mark.parametrize("wrong_subject", [False, True])
async def test_loaded_checklist_must_match_original_binding_before_confirmation(
    wrong_subject: bool,
) -> None:
    s = Scenario()
    s.recovery = IdentityRecovery(
        installation_id=INSTALLATION,
        authority=EVENT.identity.authority,
        flow_id=EVENT.flow_id if wrong_subject else IdentityRecoveryFlowId(UUID(int=99)),
        subject=IdentitySubject(str(UUID(int=99))) if wrong_subject else EVENT.identity.subject,
    )
    with pytest.raises(RuntimeError, match="original admission"):
        await s.service.record_password_saved(EVIDENCE)
    assert s.recovery.kratos_cleanup_state is State.PENDING
    assert s.events == ["begin", "read_facts", "load", "rollback"]


@pytest.mark.asyncio
async def test_initial_native_source_is_selected_before_creating_bindings() -> None:
    s = Scenario()
    s.facts = replace(
        FACTS,
        session_binding=None,
        session_admission=None,
        settings_binding=None,
        settings_admission=None,
    )
    result = await s.service.associate_settings(EVIDENCE)
    assert result is not None and result.operation_id == OPERATION
    assert s.written_admission is ADMISSION
    assert s.read_evidence is EVIDENCE
    assert s.events == ["begin", "read_facts", "associate", "commit"]


@pytest.mark.asyncio
async def test_restarted_settings_use_the_stored_session_admission() -> None:
    s = Scenario()
    evidence = replace(EVIDENCE, source_recovery_flow_id=None)
    s.facts = replace(FACTS, source_admission=None, settings_binding=None, settings_admission=None)
    result = await s.service.associate_settings(evidence)
    assert result is not None and result.operation_id == OPERATION
    assert s.written_admission is ADMISSION
    assert s.read_evidence is evidence


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        "missing_source",
        "source_identity",
        "session_identity",
        "different_recovery",
        "settings_session",
        "settings_source",
        "missing_session_admission",
    ],
)
async def test_settings_conflicts_are_rejected_before_persistence(case: str) -> None:
    s = Scenario()
    evidence = EVIDENCE
    other_identity = replace(EVENT.identity, subject=IdentitySubject(str(UUID(int=99))))
    if case == "missing_source":
        s.facts = replace(FACTS, source_admission=None, current_version=None)
    elif case == "source_identity":
        s.facts = replace(
            FACTS,
            source_admission=replace(ADMISSION, event=replace(EVENT, identity=other_identity)),
        )
    elif case == "session_identity":
        s.facts = replace(FACTS, session_binding=replace(SESSION_BINDING, identity=other_identity))
    elif case == "different_recovery":
        other = replace(
            ADMISSION,
            event=replace(EVENT, flow_id=IdentityRecoveryFlowId(UUID(int=99))),
            operation_id=OperationId("other-recovery"),
        )
        evidence = replace(EVIDENCE, source_recovery_flow_id=other.event.flow_id)
        s.facts = replace(FACTS, source_admission=other)
    elif case == "settings_session":
        s.facts = replace(
            FACTS,
            settings_binding=replace(SETTINGS_BINDING, session_id=IdentitySessionId(UUID(int=99))),
        )
    elif case == "settings_source":
        s.facts = replace(
            FACTS, settings_binding=replace(SETTINGS_BINDING, source_recovery_flow_id=None)
        )
    else:
        evidence = replace(EVIDENCE, source_recovery_flow_id=None)
        s.facts = replace(FACTS, source_admission=None, session_admission=None)
    with pytest.raises(ConflictError):
        await s.service.associate_settings(evidence)
    assert s.written_admission is None
    assert s.events == ["begin", "read_facts", "rollback"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        "missing_settings",
        "missing_bound_settings",
        "identity",
        "session",
        "missing_admission",
        "source",
    ],
)
async def test_password_conflicts_are_rejected_before_loading_or_writing(case: str) -> None:
    s = Scenario()
    evidence = EVIDENCE
    if case == "missing_settings":
        s.facts = EMPTY_FACTS
    elif case == "missing_bound_settings":
        evidence = replace(EVIDENCE, source_recovery_flow_id=None)
        s.facts = replace(FACTS, settings_binding=None)
    elif case == "identity":
        s.facts = replace(
            FACTS,
            settings_binding=replace(
                SETTINGS_BINDING,
                identity=replace(EVENT.identity, subject=IdentitySubject(str(UUID(int=99)))),
            ),
        )
    elif case == "session":
        s.facts = replace(
            FACTS,
            settings_binding=replace(SETTINGS_BINDING, session_id=IdentitySessionId(UUID(int=99))),
        )
    elif case == "missing_admission":
        s.facts = replace(FACTS, settings_admission=None)
    else:
        evidence = replace(EVIDENCE, source_recovery_flow_id=IdentityRecoveryFlowId(UUID(int=99)))
        s.facts = replace(FACTS, current_version=None)
    with pytest.raises(ConflictError):
        await s.service.record_password_saved(evidence)
    assert s.written_admission is None
    assert s.events == ["begin", "read_facts", "rollback"]


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["associate_settings", "record_password_saved"])
async def test_recovery_evidence_requires_version_state_before_persistence(operation: str) -> None:
    s = Scenario()
    s.facts = replace(FACTS, current_version=None)
    with pytest.raises(DependencyUnavailableError):
        await getattr(s.service, operation)(EVIDENCE)
    assert s.events == ["begin", "read_facts", "rollback"]


@pytest.mark.asyncio
async def test_version_unavailability_keeps_its_precedence_over_a_settings_binding_conflict() -> (
    None
):
    s = Scenario()
    s.facts = replace(
        FACTS,
        current_version=None,
        settings_binding=replace(SETTINGS_BINDING, session_id=IdentitySessionId(UUID(int=99))),
    )
    with pytest.raises(DependencyUnavailableError):
        await s.service.associate_settings(EVIDENCE)
    assert s.written_admission is None


@pytest.mark.asyncio
async def test_password_proof_can_restore_the_native_source_after_creation() -> None:
    s = Scenario()
    s.facts = replace(
        FACTS, settings_binding=replace(SETTINGS_BINDING, source_recovery_flow_id=None)
    )
    result = await s.service.record_password_saved(EVIDENCE)
    assert result is not None and result.operation_id == OPERATION


@pytest.mark.asyncio
async def test_budget_uses_the_saved_receipt_time_instead_of_a_new_clock_read() -> None:
    s = Scenario()
    s.recorded_at = RECORDED_AT - timedelta(days=1)
    await s.service.record_password_saved(EVIDENCE)
    assert s.budget is not None
    assert s.budget.started_at == s.recorded_at
    assert s.budget.deadline == s.recorded_at + timedelta(hours=1)
    assert s.budget.max_attempts == 12


@pytest.mark.asyncio
async def test_failed_password_receipt_prevents_handoff_and_commit() -> None:
    s = Scenario()
    s.receipt_error = ConflictError()
    with pytest.raises(ConflictError):
        await s.service.record_password_saved(EVIDENCE)
    assert s.events[-2:] == ["password_receipt", "rollback"]
    assert s.budget is None


@pytest.mark.asyncio
@pytest.mark.parametrize("released", [False, True])
async def test_confirmed_cleanup_does_not_create_another_handoff(released: bool) -> None:
    s = Scenario()
    s.recovery = IdentityRecovery(
        installation_id=INSTALLATION,
        authority=EVENT.identity.authority,
        flow_id=EVENT.flow_id,
        subject=EVENT.identity.subject,
        kratos_cleanup_state=State.CONFIRMED,
        hydra_cleanup_state=State.CONFIRMED,
        released_at=RECORDED_AT if released else None,
    )
    assert await s.service.record_password_saved(EVIDENCE) is not None
    assert s.events == ["begin", "read_facts", "load", "save", "password_receipt", "commit"]
    assert s.budget is None
