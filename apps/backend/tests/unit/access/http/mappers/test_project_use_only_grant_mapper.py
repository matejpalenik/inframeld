from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.mappers.project_use_only_grant_mapper import (
    ProjectUseOnlyGrantMapper,
)
from inframeld_backend.access.http.requests.project_use_only_grant_request import (
    ProjectUseOnlyGrantRequest,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


def test_http_fields_become_typed_command_values_and_canonical_retry_scope() -> None:
    request = ProjectUseOnlyGrantRequest(
        recipientPrincipalId=UUID(int=2), actionId="create-access-groups", expectedAccessRevision=7
    )
    command = ProjectUseOnlyGrantMapper.to_command(project_id=UUID(int=1), request=request)
    assert command.project_id == ProjectId(UUID(int=1))
    assert command.recipient_principal_id == PrincipalId(UUID(int=2))
    assert command.action_id == ActionId("create-access-groups")
    assert command.expected_access_revision == 7
    key = IdempotencyKey("original-grant")
    context = ProjectUseOnlyGrantMapper.to_operation_context(key)
    assert context.key == key
    assert context.method == "POST"
    assert context.requested_route == "/v1/projects/{project_id}/grants"


def test_response_preserves_original_operation_revision_and_expiry() -> None:
    """A replay describes the admitted change, even when current state has moved on."""
    command = ProjectUseOnlyGrantMapper.to_command(
        project_id=UUID(int=1),
        request=ProjectUseOnlyGrantRequest(
            recipientPrincipalId=UUID(int=2),
            actionId="create-access-groups",
            expectedAccessRevision=7,
        ),
    )
    expiry = datetime(2030, 1, 1, tzinfo=UTC)
    result = CompletedSynchronousOperationDTO(
        operation_id=OperationId("original-operation"),
        created=False,
        replay_kind=OperationReplayKind.SAFE_RESULT,
        expires_at=expiry,
    )
    response = ProjectUseOnlyGrantMapper.to_response(command=command, result=result)
    assert response.model_dump(by_alias=True) == {
        "operationId": "original-operation",
        "projectId": UUID(int=1),
        "recipientPrincipalId": UUID(int=2),
        "actionId": "create-access-groups",
        "canGrant": False,
        "accessRevision": 8,
        "idempotencyExpiresAt": expiry,
    }


def test_response_rejects_an_unsupported_internal_action() -> None:
    """Direct mapper callers receive a clear failure instead of an unrelated response."""
    command = ProjectUseOnlyGrantMapper.to_command(
        project_id=UUID(int=1),
        request=ProjectUseOnlyGrantRequest(
            recipientPrincipalId=UUID(int=2),
            actionId="create-access-groups",
            expectedAccessRevision=7,
        ),
    )
    command = replace(command, action_id=ActionId("unsupported-internal-action"))
    result = CompletedSynchronousOperationDTO(
        operation_id=OperationId("original-operation"),
        created=False,
        replay_kind=OperationReplayKind.SAFE_RESULT,
        expires_at=datetime(2030, 1, 1, tzinfo=UTC),
    )
    with pytest.raises(ValueError, match="Unsupported project grant action"):
        ProjectUseOnlyGrantMapper.to_response(command=command, result=result)
