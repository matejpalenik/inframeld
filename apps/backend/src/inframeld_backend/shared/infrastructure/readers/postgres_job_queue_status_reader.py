from sqlalchemy import DateTime, Nullable, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.shared.application.dtos.job_queue_status_dto import JobQueueStatusDTO
from inframeld_backend.shared.domain.enums.job_status import JobStatus
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow


class PostgresJobQueueStatusReader:
    """Observe current queue pressure in one bounded operational read."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def read(self) -> JobQueueStatusDTO:
        clock = func.clock_timestamp(type_=DateTime(timezone=True))
        depth, oldest, active, now = (
            (
                await self._session.execute(
                    select(
                        func.count(DurableJobRow.id),
                        Nullable(
                            func.min(DurableJobRow.admitted_at).filter(
                                DurableJobRow.status == JobStatus.QUEUED.value,
                                DurableJobRow.due_at <= clock,
                            )
                        ),
                        func.count(DurableJobRow.id).filter(
                            DurableJobRow.status == JobStatus.RUNNING.value
                        ),
                        clock,
                    ).where(
                        DurableJobRow.status.in_((JobStatus.QUEUED.value, JobStatus.RUNNING.value))
                    )
                )
            )
            .tuples()
            .one()
        )
        return JobQueueStatusDTO(
            depth,
            max(0.0, (now - oldest).total_seconds()) if oldest is not None else None,
            active > 0,
        )
