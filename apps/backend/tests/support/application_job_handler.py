import asyncio
from typing import override

from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.protocols.job_checkpoints import JobCheckpoints
from inframeld_backend.shared.application.protocols.job_handler import JobHandler


class BoundedJobHandler(JobHandler):
    """Complete three small local units through the real durable checkpoint boundary."""

    @override
    def payload_type(self) -> tuple[str, int]:
        return "test.progress", 1

    @override
    async def run(self, context: JobAttemptContextDTO, checkpoints: JobCheckpoints) -> None:
        count = (
            1
            if context.payload.data == b"slow"
            else 3
            if context.payload.data in (b"blocked", b"restart")
            else int(context.payload.data)
        )
        completed = int(context.checkpoint or b"0")
        if not 0 <= completed <= count <= 3:
            raise ValueError("The fixture work is outside its bounded range.")
        for unit in range(completed + 1, count + 1):
            await checkpoints.check(context)
            delay = (
                4.0
                if context.payload.data == b"slow"
                else 10.0
                if (
                    context.payload.data == b"blocked"
                    or (context.payload.data == b"restart" and context.attempt == 1)
                )
                and unit == 2
                else 0.25
            )
            await asyncio.sleep(delay)
            await checkpoints.save(context, str(unit).encode())
            print("fixture_unit_completed:" + str(unit), flush=True)
