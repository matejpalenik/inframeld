"""Control admission decisions without claiming database or provider qualification."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from typing import override
from uuid import UUID

from inframeld_backend.access.application.commands.admit_human_command import AdmitHumanCommand
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.human_admission_facts_dto import (
    HumanAdmissionFactsDTO,
)
from inframeld_backend.access.application.dtos.human_admission_result_dto import (
    HumanAdmissionResultDTO,
)
from inframeld_backend.access.application.dtos.human_credential_state_dto import (
    HumanCredentialStateDTO,
)
from inframeld_backend.access.application.dtos.organization_access_facts_dto import (
    OrganizationAccessFactsDTO,
)
from inframeld_backend.access.application.dtos.organization_action_grant_dto import (
    OrganizationActionGrantDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.human_admission_facts_reader import (
    HumanAdmissionFactsReader,
)
from inframeld_backend.access.application.protocols.human_admission_result_reader import (
    HumanAdmissionResultReader,
)
from inframeld_backend.access.application.protocols.human_admission_writer import (
    HumanAdmissionWriter,
)
from inframeld_backend.access.application.protocols.human_identity_verifier import (
    HumanIdentityVerifier,
)
from inframeld_backend.access.application.services.human_admission_fingerprint_service import (
    HumanAdmissionFingerprintService,
)
from inframeld_backend.access.application.services.human_admission_service import (
    HumanAdmissionService,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import (
    IdempotencyContextDTO,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from tests.support.authentication_evidence import MockAuthenticationEvidence
from tests.support.mock_project_metadata import MockOperationIdempotency

ORG = OrganizationId(UUID(int=2))
INSTALLATION = InstallationId(UUID(int=123))
AUTHORITY = IdentityAuthority("kratos:test")
IDENTITY = VerifiedHumanIdentityDTO(AUTHORITY, IdentitySubject(str(UUID(int=20))))
ALICE = Principal(PrincipalId(UUID(int=1)), ORG, PrincipalKind.HUMAN, PrincipalStatus.ACTIVE)
BOB = Principal(PrincipalId(UUID(int=3)), ORG, PrincipalKind.HUMAN, PrincipalStatus.ACTIVE)
ACCESS = AccessContextDTO(ALICE.id, MockAuthenticationEvidence.browser())
COMMAND = AdmitHumanCommand(ORG, UUID(IDENTITY.subject.value), 7)
CONTEXT = IdempotencyContextDTO(
    method=HttpMethod.POST,
    requested_route=f"/v1/organizations/{ORG.value}/human-admissions",
    key=IdempotencyKey("admit-bob"),
)
ACTOR_FACTS = OrganizationAccessFactsDTO(
    ALICE, 7, (OrganizationActionGrantDTO(ActionId("admit-users"), False),), False, None
)
FACTS = HumanAdmissionFactsDTO(
    INSTALLATION,
    IDENTITY,
    ACTOR_FACTS,
    None,
    HumanCredentialStateDTO(INSTALLATION, IDENTITY, None, False),
    False,
)


class MockAdmissionTransactions(TransactionManager):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.active = False
        self.exits = 0
        self.commit_error: BaseException | None = None

    @override
    @asynccontextmanager
    async def begin(self) -> AsyncGenerator[None]:
        assert not self.active
        self.active = True
        self.events.append("begin")
        try:
            yield
            if self.exits == 1 and self.commit_error is not None:
                raise self.commit_error
        except BaseException:
            self.events.append("rollback")
            raise
        else:
            self.events.append("commit")
        finally:
            self.active = False
            self.exits += 1


class MockAdmissionFacts(HumanAdmissionFactsReader):
    def __init__(self, owner: MockAdmissionTransactions) -> None:
        self.owner = owner
        self.preliminary: OrganizationAccessFactsDTO | None = ACTOR_FACTS
        self.final: HumanAdmissionFactsDTO | None = FACTS
        self.error: BaseException | None = None

    @override
    async def read_authorization(
        self,
        *,
        access: AccessContextDTO,
        organization_id: OrganizationId,
    ) -> OrganizationAccessFactsDTO | None:
        assert self.owner.active
        self.owner.events.append("preliminary")
        assert access.actor_principal_id == ALICE.id and organization_id == ORG
        return self.preliminary

    @override
    async def read_for_admission(
        self,
        *,
        access: AccessContextDTO,
        organization_id: OrganizationId,
        identity: VerifiedHumanIdentityDTO,
    ) -> HumanAdmissionFactsDTO | None:
        assert self.owner.active
        self.owner.events.append("fresh-facts")
        assert access.actor_principal_id == ALICE.id and organization_id == ORG
        assert identity == IDENTITY
        if self.error is not None:
            raise self.error
        return self.final


class MockAdmissionIdentityVerifier(HumanIdentityVerifier):
    def __init__(self, owner: MockAdmissionTransactions) -> None:
        self.owner = owner
        self.result: VerifiedHumanIdentityDTO | None = IDENTITY
        self.error: BaseException | None = None

    @override
    async def verify(
        self,
        identity: VerifiedHumanIdentityDTO,
        *,
        timeout_seconds: float,
    ) -> VerifiedHumanIdentityDTO | None:
        assert not self.owner.active and self.owner.exits == 1
        self.owner.events.append("verify")
        assert identity == IDENTITY and 0 < timeout_seconds <= 5
        if self.error is not None:
            raise self.error
        return self.result


class MockAdmissionWriter(HumanAdmissionWriter):
    def __init__(self, owner: MockAdmissionTransactions) -> None:
        self.owner = owner
        self.saved: Principal | None = None
        self.saved_facts: HumanAdmissionFactsDTO | None = None
        self.error: BaseException | None = None

    @override
    async def save(
        self,
        *,
        facts: HumanAdmissionFactsDTO,
        principal: Principal,
        actor_id: PrincipalId,
        operation_id: OperationId,
    ) -> None:
        assert self.owner.active and actor_id == ALICE.id
        assert operation_id == OperationId("metadata-original")
        self.owner.events.append("save")
        if self.error is not None:
            raise self.error
        self.saved = principal
        self.saved_facts = facts


class MockAdmissionResults(HumanAdmissionResultReader):
    def __init__(self, owner: MockAdmissionTransactions) -> None:
        self.owner = owner
        self.result = HumanAdmissionResultDTO(
            INSTALLATION,
            IDENTITY,
            ORG,
            ALICE.id,
            BOB.id,
            8,
            True,
            CompletedSynchronousOperationDTO(
                OperationId("metadata-original"),
                False,
                OperationReplayKind.SAFE_RESULT,
                datetime(2030, 1, 1, tzinfo=UTC),
            ),
        )

    @override
    async def original(
        self,
        *,
        installation_id: InstallationId,
        identity: VerifiedHumanIdentityDTO,
        organization_id: OrganizationId,
        actor_id: PrincipalId,
        operation: CompletedSynchronousOperationDTO,
    ) -> HumanAdmissionResultDTO:
        assert self.owner.active
        assert (installation_id, identity, organization_id, actor_id) == (
            INSTALLATION,
            IDENTITY,
            ORG,
            ALICE.id,
        )
        self.owner.events.append("original")
        return self.result


class HumanAdmissionScenario:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.transactions = MockAdmissionTransactions(self.events)
        self.facts = MockAdmissionFacts(self.transactions)
        self.verifier = MockAdmissionIdentityVerifier(self.transactions)
        self.writer = MockAdmissionWriter(self.transactions)
        self.results = MockAdmissionResults(self.transactions)
        self.idempotency = MockOperationIdempotency(self.events)
        self.fingerprints = HumanAdmissionFingerprintService(
            RequestFingerprintService(RequestFingerprintKey(b"a" * 32))
        )
        self.service = HumanAdmissionService(
            transaction_manager=self.transactions,
            admission_facts_reader=self.facts,
            admission_writer=self.writer,
            admission_result_reader=self.results,
            operation_idempotency=self.idempotency,
            admission_fingerprint_service=self.fingerprints,
            identity_verifier=self.verifier,
            identity_authority=AUTHORITY,
            identity_timeout_seconds=5,
        )

    def already_admitted(self) -> None:
        self.facts.final = replace(FACTS, principal=BOB)
