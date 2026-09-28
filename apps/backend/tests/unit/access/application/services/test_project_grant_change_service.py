from dataclasses import replace
from datetime import datetime
from typing import override
from uuid import UUID

import pytest

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_grant_change_facts_dto import (
    ProjectGrantChangeFactsDTO,
)
from inframeld_backend.access.application.protocols.project_grant_change_facts_reader import (
    ProjectGrantChangeFactsReader,
)
from inframeld_backend.access.application.protocols.project_grant_change_writer import (
    ProjectGrantChangeWriter,
)
from inframeld_backend.access.application.services.project_grant_change_service import (
    ProjectGrantChangeService,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.operation_reservation_request_dto import (
    OperationReservationRequestDTO,
)
from inframeld_backend.shared.application.dtos.operation_reservation_result_dto import (
    OperationReservationResultDTO,
)
from inframeld_backend.shared.application.dtos.project_operation_admission_request_dto import (
    ProjectOperationAdmissionRequestDTO,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.application.protocols.operation_reservation_writer import (
    OperationReservationWriter,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_id import OperationId

ACTOR_ID = PrincipalId(UUID(int=1))
RECIPIENT_ID = PrincipalId(UUID(int=2))
ORGANIZATION_ID = OrganizationId(UUID(int=3))
PROJECT_ID = ProjectId(UUID(int=4))
ACTION_ID = ActionId("create-access-groups")

FACTS = ProjectGrantChangeFactsDTO(
    actor=Principal(
        id=ACTOR_ID,
        organization_id=ORGANIZATION_ID,
        kind=PrincipalKind.HUMAN,
        status=PrincipalStatus.ACTIVE,
    ),
    recipient=Principal(
        id=RECIPIENT_ID,
        organization_id=ORGANIZATION_ID,
        kind=PrincipalKind.HUMAN,
        status=PrincipalStatus.ACTIVE,
    ),
    project_status=ProjectStatus.ACTIVE,
    project_access_revision=7,
    actor_is_project_member=True,
    recipient_is_project_member=True,
    actor_can_grant_action=False,
)


class FixedGrantFactsReader(ProjectGrantChangeFactsReader):
    def __init__(self, facts: ProjectGrantChangeFactsDTO | None) -> None:
        self._facts = facts

    @override
    async def read_for_change(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        recipient_principal_id: PrincipalId,
        action_id: ActionId,
    ) -> ProjectGrantChangeFactsDTO | None:
        return self._facts


class UnexpectedReservations(OperationReservationWriter):
    @override
    async def reserve(
        self, request: OperationReservationRequestDTO
    ) -> OperationReservationResultDTO:
        raise AssertionError("A denied grant must not reserve an operation.")

    @override
    async def mark_replayable(
        self,
        operation_id: OperationId,
        replay_kind: OperationReplayKind,
    ) -> datetime | None:
        raise AssertionError("A denied grant must not become replayable.")


class UnexpectedGrantChanges(ProjectGrantChangeWriter):
    @override
    async def create_use_only(
        self,
        *,
        organization_id: OrganizationId,
        project_id: ProjectId,
        actor_principal_id: PrincipalId,
        recipient_principal_id: PrincipalId,
        action_id: ActionId,
        expected_access_revision: int,
        operation_id: OperationId,
    ) -> None:
        raise AssertionError("A denied grant must not change Access records.")


def _service(facts: ProjectGrantChangeFactsDTO | None) -> ProjectGrantChangeService:
    return ProjectGrantChangeService(
        FixedGrantFactsReader(facts),
        UnexpectedReservations(),
        UnexpectedGrantChanges(),
    )


@pytest.mark.asyncio
async def test_use_only_authority_cannot_assign_a_grant() -> None:
    """A current use grant does not give its holder delegation authority."""
    service = _service(FACTS)
    request = ProjectOperationAdmissionRequestDTO(
        project_id=PROJECT_ID,
        method="POST",
        requested_route="/v1/projects/{project_id}/grants",
        key=IdempotencyKey("assign-bob-1"),
        fingerprint=b"x" * 32,
    )

    with pytest.raises(AccessDeniedError):
        await service.assign_use_only(
            access=AccessContextDTO(actor_principal_id=ACTOR_ID),
            request=request,
            recipient_principal_id=RECIPIENT_ID,
            action_id=ACTION_ID,
            expected_access_revision=7,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "facts",
    [
        None,
        replace(
            FACTS,
            actor=replace(FACTS.actor, status=PrincipalStatus.SUSPENDED),
        ),
        replace(FACTS, project_status=ProjectStatus.DELETING),
        replace(FACTS, actor_is_project_member=False),
    ],
)
async def test_missing_or_invisible_project_is_not_found(
    facts: ProjectGrantChangeFactsDTO | None,
) -> None:
    """Hide an unavailable project before reporting the caller's grant authority."""
    service = _service(facts)
    request = ProjectOperationAdmissionRequestDTO(
        project_id=PROJECT_ID,
        method="POST",
        requested_route="/v1/projects/{project_id}/grants",
        key=IdempotencyKey("assign-bob-1"),
        fingerprint=b"x" * 32,
    )

    with pytest.raises(ResourceNotFoundError):
        await service.assign_use_only(
            access=AccessContextDTO(actor_principal_id=ACTOR_ID),
            request=request,
            recipient_principal_id=RECIPIENT_ID,
            action_id=ACTION_ID,
            expected_access_revision=7,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("actor_can_grant", "expected_error"),
    [
        (False, AccessDeniedError),
        (True, ResourceNotFoundError),
    ],
)
async def test_missing_recipient_is_disclosed_only_to_grantor(
    actor_can_grant: bool,
    expected_error: type[Exception],
) -> None:
    """Only a current grantor may learn that the recipient is absent."""
    facts = replace(
        FACTS,
        recipient=None,
        recipient_is_project_member=False,
        actor_can_grant_action=actor_can_grant,
    )
    service = _service(facts)
    request = ProjectOperationAdmissionRequestDTO(
        project_id=PROJECT_ID,
        method="POST",
        requested_route="/v1/projects/{project_id}/grants",
        key=IdempotencyKey("assign-bob-1"),
        fingerprint=b"x" * 32,
    )

    with pytest.raises(expected_error):
        await service.assign_use_only(
            access=AccessContextDTO(actor_principal_id=ACTOR_ID),
            request=request,
            recipient_principal_id=RECIPIENT_ID,
            action_id=ACTION_ID,
            expected_access_revision=7,
        )
