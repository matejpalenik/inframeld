from typing import override
from uuid import UUID

from inframeld_backend.shared.application.dtos.human_suspension_job_binding_dto import (
    HumanSuspensionJobBindingDTO,
)
from inframeld_backend.shared.application.dtos.human_suspension_job_facts_dto import (
    HumanSuspensionJobFactsDTO,
)
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.errors.application_errors import AccessDeniedError
from inframeld_backend.shared.application.protocols.human_suspension_job_authorizer import (
    HumanSuspensionJobAuthorizer,
)
from inframeld_backend.shared.application.protocols.human_suspension_job_facts_reader import (
    HumanSuspensionJobFactsReader,
)
from inframeld_backend.shared.application.value_objects.job_payload import JobPayload
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class HumanSuspensionJobAuthorizationService(HumanSuspensionJobAuthorizer):
    """Match a caller's attempt to the current retained suspension and lease."""

    def __init__(self, facts_reader: HumanSuspensionJobFactsReader) -> None:
        self._facts_reader = facts_reader

    @override
    async def require_current(
        self, context: JobAttemptContextDTO, *, worker_id: UUID
    ) -> HumanSuspensionJobFactsDTO:
        binding = context.binding
        if (
            not isinstance(binding, HumanSuspensionJobBindingDTO)
            or binding.job_id != context.job_id
            or context.payload
            != JobPayload("human.suspension-cleanup", 1, binding.obligation_id.value.bytes)
            or type(context.attempt) is not int
            or not 1 <= context.attempt <= 3
        ):
            raise AccessDeniedError("The original suspension attempt cannot be confirmed.")

        facts = await self._facts_reader.read_live_attempt(context, worker_id=worker_id)
        if (
            facts is None
            or type(facts.attempt) is not int
            or (
                facts.binding,
                facts.payload,
                facts.attempt,
                facts.fence,
                facts.worker_id,
                facts.work_deadline,
            )
            != (
                binding,
                context.payload,
                context.attempt,
                context.fence,
                worker_id,
                context.work_deadline,
            )
        ):
            raise AccessDeniedError("The original suspension attempt cannot be confirmed.")
        times = (facts.observed_at, facts.lease_expires_at, facts.work_deadline)
        if (
            type(facts.source_revision) is not int
            or not 1 <= facts.source_revision <= RevisionValidation.MAX_VALUE
            or any(value.utcoffset() is None for value in times)
            or not facts.observed_at < facts.lease_expires_at <= facts.work_deadline
        ):
            raise AccessDeniedError("The original suspension attempt cannot be confirmed.")
        return facts
