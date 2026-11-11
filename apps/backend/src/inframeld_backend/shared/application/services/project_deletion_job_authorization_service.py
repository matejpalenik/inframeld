from typing import override

from inframeld_backend.shared.application.dtos.project_deletion_job_binding_dto import (
    ProjectDeletionJobBindingDTO,
)
from inframeld_backend.shared.application.dtos.project_deletion_job_facts_dto import (
    ProjectDeletionJobFactsDTO,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.errors.application_errors import AccessDeniedError
from inframeld_backend.shared.application.protocols.project_deletion_job_authorizer import (
    ProjectDeletionJobAuthorizer,
)
from inframeld_backend.shared.application.protocols.project_deletion_job_facts_reader import (
    ProjectDeletionJobFactsReader,
)
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class ProjectDeletionJobAuthorizationService(ProjectDeletionJobAuthorizer):
    """Match retained deletion backing without replacing product or live-fence checks."""

    def __init__(self, project_deletion_job_facts_reader: ProjectDeletionJobFactsReader) -> None:
        self._project_deletion_job_facts_reader = project_deletion_job_facts_reader

    @override
    async def require_current(
        self, job_id: JobId, binding: ProjectDeletionJobBindingDTO
    ) -> ProjectDeletionJobFactsDTO:
        facts = await self._project_deletion_job_facts_reader.read(binding.obligation_id)
        if (
            facts is None
            or facts.binding != binding
            or facts.job_id != job_id
            or (
                facts.payload.kind,
                facts.payload.version,
                facts.payload.data,
            )
            != ("project.application-shutdown", 1, binding.obligation_id.bytes)
        ):
            raise AccessDeniedError("The original Project deletion obligation cannot be confirmed.")

        original = facts.original
        if (
            (
                original.operation_id,
                original.request_id,
                original.installation_id,
                original.organization_id.value,
                original.project_id.value,
                original.initiator_principal_id.value,
                original.key,
                original.fingerprint,
            )
            != (
                binding.operation_id,
                binding.request_id,
                binding.installation_id,
                binding.organization_id,
                binding.project_id,
                binding.initiator_principal_id,
                binding.key,
                binding.fingerprint,
            )
            or original.method is not HttpMethod.DELETE
            or original.requested_route != f"/v1/projects/{binding.project_id}"
            or original.authority_family is not OperationLookupAuthorityFamily.PROJECT_ACTION_USE
            or original.action_id is None
            or original.action_id.value != "delete-project"
        ):
            raise AccessDeniedError("The original Project deletion obligation cannot be confirmed.")

        if (
            type(binding.before_access_revision) is not int
            or not 0 <= binding.before_access_revision < RevisionValidation.MAX_VALUE
            or type(binding.access_revision) is not int
            or binding.access_revision != binding.before_access_revision + 1
            or type(facts.source_revision) is not int
            or not 1 <= facts.source_revision <= RevisionValidation.MAX_VALUE
            or not self._has_coherent_progress(facts)
        ):
            raise AccessDeniedError("The original Project deletion obligation cannot be confirmed.")

        return facts

    @staticmethod
    def _has_coherent_progress(facts: ProjectDeletionJobFactsDTO) -> bool:
        """Keep completion observations ordered without inventing retention or parent expiry."""
        shutdown = facts.shutdown_completed_at
        physical = facts.physical_cleanup_completed_at
        if physical is not None and shutdown is None:
            return False

        times = (
            facts.original.recorded_at,
            facts.admitted_at,
            shutdown or facts.admitted_at,
            physical or shutdown or facts.admitted_at,
            facts.observed_at,
        )
        if any(value.utcoffset() is None for value in times):
            return False

        return all(before <= after for before, after in zip(times, times[1:], strict=False))
