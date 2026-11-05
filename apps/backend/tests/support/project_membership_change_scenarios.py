from dataclasses import replace
from typing import override
from uuid import UUID

from inframeld_backend.access.application.commands.add_project_member_command import (
    AddProjectMemberCommand,
)
from inframeld_backend.access.application.commands.remove_project_member_command import (
    RemoveProjectMemberCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.dtos.project_departure_responsibility_dto import (
    ProjectDepartureResponsibilityDTO,
)
from inframeld_backend.access.application.dtos.project_membership_change_facts_dto import (
    ProjectMembershipChangeFactsDTO,
)
from inframeld_backend.access.application.dtos.project_membership_change_result_dto import (
    ProjectMembershipChangeResultDTO,
)
from inframeld_backend.access.application.enums.project_membership_change_kind import (
    ProjectMembershipChangeKind,
)
from inframeld_backend.access.application.protocols.project_membership_change_facts_reader import (
    ProjectMembershipChangeFactsReader,
)
from inframeld_backend.access.application.protocols.project_membership_change_result_reader import (
    ProjectMembershipChangeResultReader,
)
from inframeld_backend.access.application.protocols.project_membership_change_writer import (
    ProjectMembershipChangeWriter,
)
from inframeld_backend.access.application.services.project_membership_change_fingerprint_service import (
    ProjectMembershipChangeFingerprintService,
)
from inframeld_backend.access.application.services.project_membership_change_service import (
    ProjectMembershipChangeService,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import (
    IdempotencyContextDTO,
)
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
from tests.support.mock_project_metadata import (
    NEW_RESERVATION,
    SAVED_RESULT,
    MockOperationIdempotency,
    MockTransactions,
)

ORG = OrganizationId(UUID(int=2))
PROJECT = ProjectId(UUID(int=3))
INSTALLATION = InstallationId(UUID(int=4))
ALICE = Principal(PrincipalId(UUID(int=1)), ORG, PrincipalKind.HUMAN, PrincipalStatus.ACTIVE)
BOB = Principal(PrincipalId(UUID(int=5)), ORG, PrincipalKind.HUMAN, PrincipalStatus.ACTIVE)
ACCESS = AccessContextDTO(ALICE.id, MockAuthenticationEvidence.browser())
ADD = AddProjectMemberCommand(PROJECT, BOB.id, 7)
REMOVE = RemoveProjectMemberCommand(PROJECT, BOB.id, 7)
ROUTE = f"/v1/projects/{PROJECT.value}/members/{BOB.id.value}"
ADD_CONTEXT = IdempotencyContextDTO("PUT", ROUTE, IdempotencyKey("join-bob"))
REMOVE_CONTEXT = IdempotencyContextDTO("DELETE", ROUTE, IdempotencyKey("remove-bob"))
FACTS = ProjectMembershipChangeFactsDTO(
    INSTALLATION,
    ORG,
    PROJECT,
    7,
    ProjectActionFactsDTO(ALICE, False, None, ProjectStatus.ACTIVE, True, True),
    BOB,
    False,
    True,
    False,
)


class MockMembershipFacts(ProjectMembershipChangeFactsReader):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.facts: ProjectMembershipChangeFactsDTO | None = FACTS
        self.responsibilities: tuple[ProjectDepartureResponsibilityDTO, ...] = ()

    @override
    async def lock_and_load_membership_state(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        principal_id: PrincipalId,
    ) -> ProjectMembershipChangeFactsDTO | None:
        self.events.append("facts")
        assert (
            access.actor_principal_id == ACCESS.actor_principal_id
            and project_id == PROJECT
            and principal_id == BOB.id
        )
        return self.facts

    @override
    async def load_departure_responsibilities(
        self, *, facts: ProjectMembershipChangeFactsDTO, principal_id: PrincipalId
    ) -> tuple[ProjectDepartureResponsibilityDTO, ...]:
        self.events.append("handover")
        assert facts is self.facts and principal_id == BOB.id
        return self.responsibilities


class MockMembershipWriter(ProjectMembershipChangeWriter):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.saved: (
            tuple[
                ProjectMembershipChangeFactsDTO,
                PrincipalId,
                ProjectMembershipChangeKind,
                OperationId,
            ]
            | None
        ) = None
        self.error: BaseException | None = None

    @override
    async def save(
        self,
        *,
        facts: ProjectMembershipChangeFactsDTO,
        principal_id: PrincipalId,
        change_kind: ProjectMembershipChangeKind,
        operation_id: OperationId,
    ) -> None:
        self.events.append("save")
        if self.error is not None:
            raise self.error
        self.saved = facts, principal_id, change_kind, operation_id


class MockMembershipResults(ProjectMembershipChangeResultReader):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.result = ProjectMembershipChangeResultDTO(
            INSTALLATION,
            ORG,
            PROJECT,
            ALICE.id,
            BOB.id,
            ProjectMembershipChangeKind.ADD,
            8,
            True,
            201,
            SAVED_RESULT,
        )

    @override
    async def load_original_membership_result(
        self,
        *,
        facts: ProjectMembershipChangeFactsDTO,
        principal_id: PrincipalId,
        change_kind: ProjectMembershipChangeKind,
        operation: CompletedSynchronousOperationDTO,
    ) -> ProjectMembershipChangeResultDTO:
        self.events.append("original")
        return self.result


class MembershipChangeScenario:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.transactions = MockTransactions(self.events)
        self.facts = MockMembershipFacts(self.events)
        self.writer = MockMembershipWriter(self.events)
        self.results = MockMembershipResults(self.events)
        self.idempotency = MockOperationIdempotency(self.events)
        self.idempotency.result = NEW_RESERVATION
        self.fingerprints = ProjectMembershipChangeFingerprintService(
            RequestFingerprintService(RequestFingerprintKey(b"m" * 32))
        )
        self.service = ProjectMembershipChangeService(
            transaction_manager=self.transactions,
            membership_facts_reader=self.facts,
            membership_change_writer=self.writer,
            membership_result_reader=self.results,
            operation_idempotency=self.idempotency,
            membership_fingerprint_service=self.fingerprints,
        )

    def member(self) -> None:
        assert self.facts.facts is not None
        self.facts.facts = replace(self.facts.facts, recipient_is_project_member=True)
