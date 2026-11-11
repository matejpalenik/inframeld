"""Keep every status observation inside the delivered database deadline without real I/O."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.engine import Result
from sqlalchemy.engine.result import IteratorResult, SimpleResultMetaData
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.deletion_status_authorization_dto import (
    DeletionStatusAuthorizationDTO,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.readers.postgres_deletion_status_reader import (
    PostgresDeletionStatusReader,
)
from inframeld_backend.shared.infrastructure.rows.deletion_status_binding_row import (
    DeletionStatusBindingRow,
)
from inframeld_backend.shared.infrastructure.rows.deletion_status_observation_row import (
    DeletionStatusObservationRow,
)


def retained_query() -> tuple[
    DeletionStatusAuthorizationDTO,
    Result[tuple[DeletionStatusBindingRow, DeletionStatusObservationRow | None, datetime]],
]:
    now = datetime.now(UTC)
    project_id = uuid4()
    retained = DeletionStatusBindingRow(
        operation_id="original-delete",
        request_id=uuid4(),
        installation_id=uuid4(),
        organization_id=uuid4(),
        project_id=project_id,
        initiator_principal_id=uuid4(),
        method="DELETE",
        requested_route=f"/v1/projects/{project_id}",
        request_key="original-key",
        request_fingerprint=b"f" * 32,
        authority_family="project_action_use",
        action_id="delete-project",
        retention_days=30,
        retention_policy_version="ADR-0117/PD-KNOWLEDGE-02:v1",
    )
    retained.recorded_at = now
    authorization = DeletionStatusAuthorizationDTO(
        OperationId(retained.operation_id),
        InstallationId(retained.installation_id),
        OrganizationId(retained.organization_id),
        PrincipalId(retained.initiator_principal_id),
    )
    result: Result[
        tuple[DeletionStatusBindingRow, DeletionStatusObservationRow | None, datetime]
    ] = IteratorResult(
        SimpleResultMetaData(["binding", "owner", "observed_at"]), iter([(retained, None, now)])
    )
    return authorization, result


@pytest.mark.asyncio
async def test_stalled_parent_observation_uses_the_same_existing_five_second_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authorization, result = retained_query()
    entered, canceled = asyncio.Event(), asyncio.Event()

    async def stalled(*args: object, **kwargs: object) -> None:
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            canceled.set()

    async with AsyncSession() as session, session.begin():
        monkeypatch.setattr(session, "execute", AsyncMock(return_value=result))
        monkeypatch.setattr(session, "scalar", AsyncMock(side_effect=stalled))
        # This outer bound only detects an escaped production deadline.
        async with asyncio.timeout(6):
            with pytest.raises(DependencyUnavailableError):
                await PostgresDeletionStatusReader(session).read(authorization=authorization)
    assert entered.is_set() and canceled.is_set()


@pytest.mark.asyncio
async def test_followup_operational_failure_has_the_same_availability_translation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authorization, result = retained_query()
    failure = OperationalError("controlled query", {}, OSError("controlled unavailable database"))
    async with AsyncSession() as session, session.begin():
        monkeypatch.setattr(session, "execute", AsyncMock(return_value=result))
        monkeypatch.setattr(session, "scalar", AsyncMock(side_effect=failure))
        with pytest.raises(DependencyUnavailableError):
            await PostgresDeletionStatusReader(session).read(authorization=authorization)


@pytest.mark.asyncio
async def test_cancellation_of_followup_observation_propagates_and_settles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authorization, result = retained_query()
    entered, canceled = asyncio.Event(), asyncio.Event()

    async def stalled(*args: object, **kwargs: object) -> None:
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            canceled.set()

    async with AsyncSession() as session, session.begin():
        monkeypatch.setattr(session, "execute", AsyncMock(return_value=result))
        monkeypatch.setattr(session, "scalar", AsyncMock(side_effect=stalled))
        task = asyncio.create_task(
            PostgresDeletionStatusReader(session).read(authorization=authorization)
        )
        try:
            async with asyncio.timeout(1):
                await entered.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            if not task.done():
                task.cancel()
            async with asyncio.timeout(1):
                await asyncio.shield(asyncio.gather(task, return_exceptions=True))
    assert canceled.is_set()
