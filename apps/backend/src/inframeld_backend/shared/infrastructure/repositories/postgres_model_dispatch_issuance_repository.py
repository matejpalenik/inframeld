from datetime import timedelta
from typing import override

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.dtos.model_dispatch_issuance_dto import (
    ModelDispatchIssuanceDTO,
)
from inframeld_backend.shared.application.errors.application_errors import ConflictError
from inframeld_backend.shared.application.errors.job_errors import (
    JobFenceLostError,
    JobStoppedError,
)
from inframeld_backend.shared.application.protocols.model_dispatch_issuance_repository import (
    ModelDispatchIssuanceRepository,
)
from inframeld_backend.shared.application.value_objects.job_fence import JobFence
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.application.value_objects.model_call_id import ModelCallId
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId
from inframeld_backend.shared.infrastructure.repositories.postgres_job_store import PostgresJobStore
from inframeld_backend.shared.infrastructure.rows.model_dispatch_issuance_row import (
    ModelDispatchIssuanceRow,
)


class PostgresModelDispatchIssuanceRepository(ModelDispatchIssuanceRepository):
    """Use the existing ordinary job marker without interpreting it as evidence to send."""

    def __init__(self, session: AsyncSession, jobs: PostgresJobStore) -> None:
        self._session = session
        self._jobs = jobs

    @override
    async def add(
        self, attempt: JobAttemptContextDTO, issuance: ModelDispatchIssuanceDTO
    ) -> timedelta:
        if (
            issuance.job_id != attempt.job_id
            or issuance.attempt_number != attempt.attempt
            or issuance.fence != attempt.fence
        ):
            raise ConflictError("The model issuance must match its original attempt.")
        current = await self._jobs.require_current(attempt)
        if current.cancel_requested:
            raise JobStoppedError("Canceled work cannot issue a model call.")
        if current.checkpoint:
            raise ConflictError("The original one-call embedding job already has progress.")
        if current.lease_expires_at is None or current.work_deadline is None:
            raise JobFenceLostError("The model issuance requires a bounded original lease.")

        row = ModelDispatchIssuanceRow
        inserted = await self._session.scalar(
            insert(row)
            .values(
                call_id=issuance.call_id.value,
                job_id=issuance.job_id.value,
                attempt_number=issuance.attempt_number,
                fence=issuance.fence.value,
                connection_id=issuance.connection_id.value,
                access_revision=issuance.access_revision,
                credential_revision=issuance.credential_revision,
                adapter_revision=issuance.adapter_revision,
            )
            .on_conflict_do_nothing(index_elements=[row.call_id])
            .returning(row.call_id)
        )
        if inserted is None:
            raise ConflictError("The original model call was already issued.")
        await self._jobs.begin_effect(attempt, self._unit(issuance.call_id))
        return min(current.work_deadline, current.lease_expires_at) - current.observed_at

    @override
    async def get(self, call_id: ModelCallId) -> ModelDispatchIssuanceDTO | None:
        if not self._session.in_transaction():
            raise RuntimeError("Model issuance requires its caller transaction.")
        row = await self._session.get(ModelDispatchIssuanceRow, call_id.value)
        if row is None:
            return None
        return ModelDispatchIssuanceDTO(
            ModelCallId(row.call_id),
            JobId(row.job_id),
            row.attempt_number,
            JobFence(row.fence),
            ModelConnectionId(row.connection_id),
            row.access_revision,
            row.credential_revision,
            row.adapter_revision,
        )

    @override
    async def confirm(
        self, attempt: JobAttemptContextDTO, call_id: ModelCallId, checkpoint: bytes
    ) -> bool:
        current = await self._jobs.require_current(attempt)
        if current.cancel_requested:
            await self._jobs.confirm_effect(attempt, self._unit(call_id), current.checkpoint)
            return False
        if current.checkpoint:
            raise ConflictError("The original model progress changed before confirmation.")
        await self._jobs.confirm_effect(attempt, self._unit(call_id), checkpoint)
        return True

    @staticmethod
    def _unit(call_id: ModelCallId) -> str:
        return f"model-call:{call_id.value}"
