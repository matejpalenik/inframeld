"""Keep ordinary deletion authority distinct from retained initiator recovery."""

from dataclasses import replace
from datetime import timedelta
from typing import override
from uuid import UUID

import pytest
from tests.support.mock_project_metadata import (
    ACCESS,
    NEW_RESERVATION,
    ORGANIZATION_ID,
    PROJECT_ID,
    SAVED_RESULT,
    MockOperationIdempotency,
    MockTransactions,
)

from inframeld_backend.access.application.commands.delete_access_group_command import (
    DeleteAccessGroupCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.access_group_metadata_dto import (
    AccessGroupMetadataDTO,
)
from inframeld_backend.access.application.dtos.access_group_read_facts_dto import (
    AccessGroupReadFactsDTO,
)
from inframeld_backend.access.application.dtos.deleted_access_group_dto import DeletedAccessGroupDTO
from inframeld_backend.access.application.dtos.human_credential_facts_dto import (
    HumanCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.protocols.access_group_deletion_facts_reader import (
    AccessGroupDeletionFactsReader,
)
from inframeld_backend.access.application.protocols.access_group_deletion_result_reader import (
    AccessGroupDeletionResultReader,
)
from inframeld_backend.access.application.protocols.access_group_deletion_writer import (
    AccessGroupDeletionWriter,
)
from inframeld_backend.access.application.services.access_group_deletion_service import (
    AccessGroupDeletionService,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.deletion_status_binding_dto import (
    DeletionStatusBindingDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
)
from inframeld_backend.shared.application.dtos.operation_reservation_request_dto import (
    OperationReservationRequestDTO,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    ResourceNotFoundError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.protocols.deletion_status_binding_writer import (
    DeletionStatusBindingWriter,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName

GROUP = AccessGroupId(UUID(int=10))
REQUEST = RequestId(UUID(int=12))
COMMAND = DeleteAccessGroupCommand(PROJECT_ID, GROUP, 7)
CONTEXT = IdempotencyContextDTO(
    HttpMethod.DELETE,
    f"/v1/projects/{PROJECT_ID.value}/access-groups/{GROUP.value}",
    IdempotencyKey("delete-original"),
)
FACTS = AccessGroupReadFactsDTO(
    installation_id=InstallationId(UUID(int=20)),
    group=AccessGroupMetadataDTO(
        organization_id=ORGANIZATION_ID,
        project_id=PROJECT_ID,
        group_id=GROUP,
        name=ResourceName("support"),
        display_name="Support",
        created_at=SAVED_RESULT.expires_at,
        access_revision=7,
    ),
    action=ProjectActionFactsDTO(
        principal=Principal(
            ACCESS.actor_principal_id, ORGANIZATION_ID, PrincipalKind.HUMAN, PrincipalStatus.ACTIVE
        ),
        has_pending_recovery=False,
        oauth_credential_facts=HumanCredentialFactsDTO(True, HumanCredentialVersion(1)),
        project_status=ProjectStatus.ACTIVE,
        is_project_member=True,
        has_exact_action_grant=True,
    ),
    is_member=True,
    is_manager=True,
    has_group_action=False,
)
ORIGINAL = DeletedAccessGroupDTO(
    operation_id=SAVED_RESULT.operation_id,
    organization_id=ORGANIZATION_ID,
    project_id=PROJECT_ID,
    group_id=GROUP,
    actor_principal_id=ACCESS.actor_principal_id,
    access_revision=8,
)


class MockFacts(AccessGroupDeletionFactsReader):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.result: AccessGroupReadFactsDTO | None = FACTS

    @override
    async def lock_for_deletion(
        self, *, access: AccessContextDTO, project_id: ProjectId, group_id: AccessGroupId
    ) -> AccessGroupReadFactsDTO | None:
        self.events.append("authorize")
        return self.result


class MockWriter(AccessGroupDeletionWriter):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.groups: list[DeletedAccessGroupDTO] = []
        self.error: Exception | None = None

    @override
    async def delete(
        self,
        *,
        group: DeletedAccessGroupDTO,
        expected_project_revision: int,
        binding: DeletionStatusBindingDTO,
    ) -> None:
        self.events.append("delete")
        self.groups.append(group)
        assert (
            group.access_revision == expected_project_revision + 1
            and binding.operation_id == group.operation_id
        )
        if self.error is not None:
            raise self.error


class MockResults(AccessGroupDeletionResultReader):
    def __init__(self, events: list[str]) -> None:
        self.events = events

    @override
    async def original(
        self,
        *,
        organization_id: OrganizationId,
        actor_id: PrincipalId,
        command: DeleteAccessGroupCommand,
        operation_id: OperationId,
    ) -> DeletedAccessGroupDTO:
        self.events.append("original")
        return ORIGINAL


class MockBinding(DeletionStatusBindingWriter):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.request: OperationReservationRequestDTO | None = None

    @override
    async def bind_original_request(
        self,
        *,
        reservation: NewOperationReservationDTO,
        request_id: RequestId,
        expected_installation_id: InstallationId,
        expected_request: OperationReservationRequestDTO,
    ) -> DeletionStatusBindingDTO:
        self.events.append("bind")
        self.request = expected_request
        assert expected_request.lookup_authority is not None
        assert expected_request.project_id is not None
        return DeletionStatusBindingDTO(
            operation_id=reservation.operation_id,
            request_id=request_id,
            installation_id=expected_installation_id,
            organization_id=expected_request.organization_id,
            project_id=expected_request.project_id,
            initiator_principal_id=expected_request.principal_id,
            method=expected_request.method,
            requested_route=expected_request.requested_route,
            key=expected_request.key,
            fingerprint=RequestFingerprint(expected_request.fingerprint),
            authority_family=expected_request.lookup_authority.family,
            action_id=expected_request.lookup_authority.action_id,
            recorded_at=SAVED_RESULT.expires_at - timedelta(days=1),
            retention_days=30,
            retention_policy_version="ADR-0117/PD-KNOWLEDGE-02:v1",
        )


class DeletionScenario:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.facts, self.writer, self.binding = (
            MockFacts(self.events),
            MockWriter(self.events),
            MockBinding(self.events),
        )
        self.idempotency = MockOperationIdempotency(self.events)
        self.idempotency.result = NEW_RESERVATION
        self.service = AccessGroupDeletionService(
            transaction_manager=MockTransactions(self.events),
            group_deletion_facts_reader=self.facts,
            group_deletion_writer=self.writer,
            group_deletion_result_reader=MockResults(self.events),
            operation_idempotency=self.idempotency,
            request_fingerprint_service=RequestFingerprintService(RequestFingerprintKey(b"K" * 32)),
            deletion_status_binding_writer=self.binding,
        )

    async def delete(self, command: DeleteAccessGroupCommand = COMMAND):
        return await self.service.delete(
            access=ACCESS, command=command, context=CONTEXT, request_id=REQUEST
        )


@pytest.mark.asyncio
async def test_deletion_binds_original_identity_and_completion_in_one_transaction() -> None:
    scenario = DeletionScenario()
    result = await scenario.delete()
    assert result.group == ORIGINAL and scenario.writer.groups == [ORIGINAL]
    assert scenario.events == [
        "begin",
        "authorize",
        "reserve",
        "bind",
        "delete",
        "complete",
        "commit",
    ]
    assert (
        scenario.binding.request is not None
        and scenario.binding.request.requested_route == CONTEXT.requested_route
    )
    assert scenario.binding.request.lookup_authority is not None
    assert scenario.binding.request.lookup_authority.action_id.value == "delete-access-group"


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["absent", "not-manager", "recovery"])
async def test_current_management_is_required_before_ordinary_history(change: str) -> None:
    scenario = DeletionScenario()
    scenario.idempotency.result = SAVED_RESULT
    if change == "absent":
        scenario.facts.result = None
    else:
        scenario.facts.result = replace(
            FACTS,
            action=replace(
                FACTS.action,
                has_exact_action_grant=change != "not-manager",
                has_pending_recovery=change == "recovery",
            ),
            is_manager=change != "not-manager",
        )
    with pytest.raises((AccessDeniedError, ResourceNotFoundError)):
        await scenario.delete()
    assert scenario.idempotency.calls == 0 and scenario.binding.request is None


@pytest.mark.asyncio
async def test_ordinary_replay_never_rebinds_or_deletes_again() -> None:
    scenario = DeletionScenario()
    scenario.idempotency.result = SAVED_RESULT
    scenario.facts.result = replace(FACTS, group=replace(FACTS.group, access_revision=90))
    result = await scenario.delete()
    assert result.group == ORIGINAL and not scenario.writer.groups
    assert scenario.events == ["begin", "authorize", "reserve", "original", "commit"]


@pytest.mark.asyncio
async def test_stale_or_protected_delete_does_not_complete() -> None:
    scenario = DeletionScenario()
    with pytest.raises(StaleRevisionError):
        await scenario.delete(replace(COMMAND, expected_access_revision=6))
    assert scenario.binding.request is None
    scenario.writer.error = ConflictError("A real stored reference restricts deletion.")
    with pytest.raises(ConflictError):
        await scenario.delete()
    assert "complete" not in scenario.events and scenario.events[-1] == "rollback"
