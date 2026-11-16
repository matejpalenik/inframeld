import asyncio

from inframeld_backend.access.application.dtos.model_dispatch_credential_dto import (
    ModelDispatchCredentialDTO,
)
from inframeld_backend.access.application.protocols.admitted_work_authorizer import (
    AdmittedWorkAuthorizer,
)
from inframeld_backend.access.application.protocols.model_dispatch_credential_reader import (
    ModelDispatchCredentialReader,
)
from inframeld_backend.access.domain.enums.model_connection_authentication import (
    ModelConnectionAuthentication,
)
from inframeld_backend.access.domain.policies.model_connection_destination_policy import (
    ModelConnectionDestinationPolicy,
)
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.dtos.product_job_binding_dto import ProductJobBindingDTO
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    DependencyUnavailableError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.errors.job_errors import JobStoppedError
from inframeld_backend.shared.application.protocols.job_ownership import JobOwnership
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class ModelDispatchCredentialService:
    """Read the current sealed credential within the caller's short READ COMMITTED transaction.

    All database participants share the caller's session so the identity, Organization,
    Project and job locks protect the read in that order. A failed read must roll back
    the caller's transaction.
    """

    def __init__(
        self,
        admitted_work_authorizer: AdmittedWorkAuthorizer,
        job_ownership: JobOwnership,
        credential_reader: ModelDispatchCredentialReader,
        destination_policy: ModelConnectionDestinationPolicy,
    ) -> None:
        self._admitted_work_authorizer = admitted_work_authorizer
        self._job_ownership = job_ownership
        self._credential_reader = credential_reader
        self._destination_policy = destination_policy

    async def read(
        self,
        *,
        attempt: JobAttemptContextDTO,
        connection_id: ModelConnectionId,
        admitted_access_revision: int,
    ) -> ModelDispatchCredentialDTO:
        """Use the selection and revision from the caller's original admitted work.

        The product job binding alone does not establish that selection. This
        operation returns a snapshot and grants no authority to send a request.
        """
        if not isinstance(attempt.binding, ProductJobBindingDTO):
            raise AccessDeniedError("Provider credentials require an admitted product job.")
        RevisionValidation.require(admitted_access_revision)
        authority = attempt.binding.authority
        await self._admitted_work_authorizer.require_current(authority)
        try:
            async with asyncio.timeout(5):
                job = await self._job_ownership.require_current(attempt)
        except TimeoutError:
            raise DependencyUnavailableError(
                "Current job ownership exceeded its database deadline."
            ) from None
        if job.cancel_requested:
            raise JobStoppedError("The original product job was canceled.")

        current = await self._credential_reader.read_access(authority, connection_id)
        if current is None:
            raise AccessDeniedError("The selected model connection is unavailable to this job.")
        access, access_revision = current
        if access_revision != admitted_access_revision:
            raise StaleRevisionError("The selected model connection revision is no longer current.")
        if not self._destination_policy.permits(
            provider=access.provider,
            base_url=access.base_url,
            api_version=access.api_version,
            authentication=access.authentication,
        ):
            raise AccessDeniedError("The selected model destination is no longer approved.")
        if access.authentication is not ModelConnectionAuthentication.API_KEY:
            raise ConflictError("This credential reader requires an API-key connection.")

        sealed = await self._credential_reader.read_sealed(
            authority, connection_id, access_revision
        )
        if sealed is None:
            raise ConflictError("A current provider credential is required for this connection.")
        binding, envelope = sealed
        if (
            binding.organization_id != authority.organization_id
            or binding.project_id != authority.project_id
            or binding.connection_id != connection_id
            or not 1 <= binding.revision <= RevisionValidation.MAX_VALUE
        ):
            raise DependencyUnavailableError("The stored provider credential is unavailable.")
        return ModelDispatchCredentialDTO(access, access_revision, binding, envelope)
