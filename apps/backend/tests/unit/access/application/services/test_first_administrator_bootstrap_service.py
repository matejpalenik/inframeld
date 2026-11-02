import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import override
from uuid import UUID

import pytest

from inframeld_backend.access.application.commands.bootstrap_first_administrator_command import (
    BootstrapFirstAdministratorCommand,
)
from inframeld_backend.access.application.dtos.first_administrator_bootstrap_facts_dto import (
    FirstAdministratorBootstrapFactsDTO,
)
from inframeld_backend.access.application.dtos.first_administrator_bootstrap_receipt_dto import (
    FirstAdministratorBootstrapReceiptDTO,
)
from inframeld_backend.access.application.dtos.human_credential_state_dto import (
    HumanCredentialStateDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.first_administrator_bootstrap_error_code import (
    FirstAdministratorBootstrapErrorCode as Code,
)
from inframeld_backend.access.application.errors.first_administrator_bootstrap_error import (
    FirstAdministratorBootstrapError,
)
from inframeld_backend.access.application.protocols.first_administrator_bootstrap_facts_reader import (
    FirstAdministratorBootstrapFactsReader,
)
from inframeld_backend.access.application.protocols.first_administrator_bootstrap_writer import (
    FirstAdministratorBootstrapWriter,
)
from inframeld_backend.access.application.protocols.human_access_token_verifier import (
    HumanAccessTokenVerifier,
)
from inframeld_backend.access.application.protocols.human_identity_verifier import (
    HumanIdentityVerifier,
)
from inframeld_backend.access.application.services.first_administrator_bootstrap_fingerprint_service import (
    FirstAdministratorBootstrapFingerprintService,
)
from inframeld_backend.access.application.services.first_administrator_bootstrap_service import (
    FirstAdministratorBootstrapService,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


class MockTokenVerifier(HumanAccessTokenVerifier):
    def __init__(self, events: list[str], binding: HumanOAuthCredentialBindingDTO) -> None:
        self.events = events
        self.binding: HumanOAuthCredentialBindingDTO | None = binding
        self.error: Exception | None = None

    @override
    async def verify(
        self, credential: HumanAccessTokenCredential, *, timeout_seconds: float
    ) -> HumanOAuthCredentialBindingDTO | None:
        assert 0 < timeout_seconds <= 5
        self.events.append("token")
        if self.error:
            raise self.error
        return self.binding


class MockIdentityVerifier(HumanIdentityVerifier):
    def __init__(self, events: list[str], identity: VerifiedHumanIdentityDTO) -> None:
        self.events = events
        self.identity: VerifiedHumanIdentityDTO | None = identity

    @override
    async def verify(
        self, identity: VerifiedHumanIdentityDTO, *, timeout_seconds: float
    ) -> VerifiedHumanIdentityDTO | None:
        assert 0 < timeout_seconds <= 5
        self.events.append("identity")
        return self.identity


class MockTransactions(TransactionManager):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.fail_commit = False

    @override
    @asynccontextmanager
    async def begin(self) -> AsyncGenerator[None]:
        self.events.append("begin")
        try:
            yield
        except BaseException:
            self.events.append("rollback")
            raise
        if self.fail_commit:
            self.events.append("commit-unknown")
            raise RuntimeError("Controlled commit failure")
        self.events.append("commit")


class MockFacts(FirstAdministratorBootstrapFactsReader):
    def __init__(self, events: list[str], current: FirstAdministratorBootstrapFactsDTO) -> None:
        self.events = events
        self.current = current
        self.stored: FirstAdministratorBootstrapReceiptDTO | None = None

    @override
    async def read(
        self, *, installation_id: InstallationId, identity: VerifiedHumanIdentityDTO
    ) -> FirstAdministratorBootstrapFactsDTO:
        self.events.append("facts")
        return self.current

    @override
    async def receipt(
        self, *, installation_id: InstallationId, operation_id: OperationId
    ) -> FirstAdministratorBootstrapReceiptDTO | None:
        self.events.append("receipt")
        return self.stored


class MockWriter(FirstAdministratorBootstrapWriter):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.receipts: list[FirstAdministratorBootstrapReceiptDTO] = []
        self.error: Exception | None = None
        self.reserved = True
        self.pause: asyncio.Event | None = None
        self.entered = asyncio.Event()

    @override
    async def bootstrap(
        self,
        *,
        facts: FirstAdministratorBootstrapFactsDTO,
        receipt: FirstAdministratorBootstrapReceiptDTO,
    ) -> bool:
        self.events.append("write")
        self.receipts.append(receipt)
        self.entered.set()
        if self.pause:
            await self.pause.wait()
        if self.error:
            raise self.error
        return self.reserved


@dataclass
class BootstrapScenarioDTO:
    service: FirstAdministratorBootstrapService
    command: BootstrapFirstAdministratorCommand
    events: list[str]
    token: MockTokenVerifier
    identity: MockIdentityVerifier
    facts: MockFacts
    writer: MockWriter
    transactions: MockTransactions


@pytest.fixture
def scenario() -> BootstrapScenarioDTO:
    identity = VerifiedHumanIdentityDTO(
        IdentityAuthority("kratos:test"), IdentitySubject(str(UUID(int=2)))
    )
    installed = InstallationId(UUID(int=1))
    binding = HumanOAuthCredentialBindingDTO(identity, installed, HumanCredentialVersion(1))
    facts = FirstAdministratorBootstrapFactsDTO(
        installed,
        identity,
        HumanCredentialStateDTO(installed, identity, binding.version, False),
        None,
        False,
        False,
        datetime(2026, 1, 1, tzinfo=UTC),
    )
    events: list[str] = []
    token = MockTokenVerifier(events, binding)
    verifier = MockIdentityVerifier(events, identity)
    reader = MockFacts(events, facts)
    writer = MockWriter(events)
    transactions = MockTransactions(events)
    return BootstrapScenarioDTO(
        FirstAdministratorBootstrapService(
            token_verifier=token,
            identity_verifier=verifier,
            transactions=transactions,
            facts=reader,
            writer=writer,
            fingerprints=FirstAdministratorBootstrapFingerprintService(
                RequestFingerprintService(RequestFingerprintKey(b"k" * 32))
            ),
        ),
        BootstrapFirstAdministratorCommand(
            installed,
            OperationId("first-claim"),
            0,
            UUID(int=2),
            "Operator",
            "First admission",
            HumanAccessTokenCredential("private-proof"),
        ),
        events,
        token,
        verifier,
        reader,
        writer,
        transactions,
    )


@pytest.mark.asyncio
async def test_verified_absent_account_claim_commits_only_after_provider_checks(
    scenario: BootstrapScenarioDTO,
) -> None:
    result = await scenario.service.bootstrap(scenario.command)

    assert result.operation_id == scenario.command.operation_id
    assert result.installation_id == scenario.command.expected_installation_id
    assert result.access_revision == 1
    assert scenario.events == ["token", "identity", "begin", "facts", "receipt", "write", "commit"]
    assert len(scenario.writer.receipts) == 1
    assert "private-proof" not in repr(scenario.writer.receipts[0])


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["token", "identity", "installation"])
async def test_rejected_provider_proof_never_opens_local_state(
    scenario: BootstrapScenarioDTO, boundary: str
) -> None:
    if boundary == "token":
        scenario.token.binding = None
    elif boundary == "identity":
        scenario.identity.identity = None
    else:
        assert scenario.token.binding is not None
        scenario.token.binding = replace(
            scenario.token.binding, installation_id=InstallationId(UUID(int=9))
        )

    with pytest.raises(FirstAdministratorBootstrapError):
        await scenario.service.bootstrap(scenario.command)

    assert "begin" not in scenario.events
    assert scenario.writer.receipts == []


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["blocked", "wrong-version", "missing-version"])
async def test_current_recovery_and_generation_checks_precede_original_lookup(
    scenario: BootstrapScenarioDTO, state: str
) -> None:
    current = scenario.facts.current.credential_state
    current = (
        replace(current, has_pending_recovery=True)
        if state == "blocked"
        else replace(
            current, version=HumanCredentialVersion(2) if state == "wrong-version" else None
        )
    )
    scenario.facts.current = replace(scenario.facts.current, credential_state=current)

    with pytest.raises(FirstAdministratorBootstrapError) as error:
        await scenario.service.bootstrap(scenario.command)

    assert error.value.code == (
        Code.IDENTITY_INELIGIBLE if state == "blocked" else Code.INVALID_IDENTITY_PROOF
    )
    assert "receipt" not in scenario.events
    assert scenario.events[-1] == "rollback"
    assert scenario.writer.receipts == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("business", "claimed", "revision", "code"),
    [
        (True, False, 0, Code.DEPENDENCY_UNAVAILABLE),
        (True, True, 0, Code.ALREADY_BOOTSTRAPPED),
        (False, False, 2, Code.STALE_REVISION),
    ],
)
async def test_nonpristine_or_stale_claim_does_not_write(
    scenario: BootstrapScenarioDTO, business: bool, claimed: bool, revision: int, code: Code
) -> None:
    scenario.facts.current = replace(
        scenario.facts.current, has_business_state=business, has_bootstrap_claim=claimed
    )
    with pytest.raises(FirstAdministratorBootstrapError) as error:
        await scenario.service.bootstrap(
            replace(scenario.command, expected_access_revision=revision)
        )
    assert error.value.code == code
    assert scenario.writer.receipts == []


@pytest.mark.asyncio
async def test_replay_verifies_fresh_proof_and_returns_original_without_regrant(
    scenario: BootstrapScenarioDTO,
) -> None:
    original = await scenario.service.bootstrap(scenario.command)
    scenario.facts.stored = scenario.writer.receipts[0]
    assert scenario.token.binding is not None
    refreshed = replace(scenario.token.binding, version=HumanCredentialVersion(2))
    scenario.token.binding = refreshed
    scenario.facts.current = replace(
        scenario.facts.current,
        principal=Principal(
            original.recipient_id,
            original.organization_id,
            PrincipalKind.HUMAN,
            PrincipalStatus.ACTIVE,
        ),
        credential_state=replace(
            scenario.facts.current.credential_state, version=refreshed.version
        ),
        has_business_state=True,
        has_bootstrap_claim=True,
    )
    scenario.events.clear()
    result = await scenario.service.bootstrap(
        replace(scenario.command, identity_proof=HumanAccessTokenCredential("refreshed-proof"))
    )
    assert result == original
    assert scenario.events == ["token", "identity", "begin", "facts", "receipt", "commit"]
    assert len(scenario.writer.receipts) == 1

    with pytest.raises(FirstAdministratorBootstrapError) as error:
        await scenario.service.bootstrap(replace(scenario.command, reason="Different meaning"))
    assert error.value.code == Code.KEY_REUSED
    assert len(scenario.writer.receipts) == 1


@pytest.mark.asyncio
async def test_audit_persistence_and_uncertain_commit_fail_without_automatic_retry(
    scenario: BootstrapScenarioDTO,
) -> None:
    scenario.writer.error = RuntimeError("Required audit unavailable")
    with pytest.raises(RuntimeError, match="Required audit"):
        await scenario.service.bootstrap(scenario.command)
    assert scenario.events[-1] == "rollback"
    assert len(scenario.writer.receipts) == 1

    scenario.writer.error = None
    scenario.transactions.fail_commit = True
    with pytest.raises(RuntimeError, match="Controlled commit"):
        await scenario.service.bootstrap(scenario.command)
    assert len(scenario.writer.receipts) == 2
    assert scenario.events[-1] == "commit-unknown"


@pytest.mark.asyncio
async def test_cancellation_propagates_through_the_owning_transaction(
    scenario: BootstrapScenarioDTO,
) -> None:
    scenario.writer.pause = asyncio.Event()
    task = asyncio.create_task(scenario.service.bootstrap(scenario.command))
    try:
        await asyncio.wait_for(scenario.writer.entered.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert scenario.events[-1] == "rollback"
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
