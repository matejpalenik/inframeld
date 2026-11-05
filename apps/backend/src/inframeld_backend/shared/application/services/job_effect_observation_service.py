from typing import override

from inframeld_backend.access.application.protocols.admitted_work_authorizer import (
    AdmittedWorkAuthorizer,
)
from inframeld_backend.shared.application.dtos.artifact_attempt_dto import ArtifactAttemptDTO
from inframeld_backend.shared.application.dtos.artifact_cleanup_job_binding_dto import (
    ArtifactCleanupJobBindingDTO,
)
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.dtos.job_effect_binding_dto import JobEffectBindingDTO
from inframeld_backend.shared.application.dtos.job_effect_observation_dto import (
    JobEffectObservationDTO,
)
from inframeld_backend.shared.application.dtos.product_job_binding_dto import ProductJobBindingDTO
from inframeld_backend.shared.application.enums.job_effect_action import JobEffectAction
from inframeld_backend.shared.application.errors.application_errors import ConflictError
from inframeld_backend.shared.application.errors.job_errors import JobStoppedError
from inframeld_backend.shared.application.protocols.artifact_cleanup_authorizer import (
    ArtifactCleanupAuthorizer,
)
from inframeld_backend.shared.application.protocols.job_effect_observation_recorder import (
    JobEffectObservationRecorder,
)
from inframeld_backend.shared.application.protocols.job_store import JobStore
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.job_effect_id import JobEffectId


class JobEffectObservationService(JobEffectObservationRecorder):
    """Own one short exact invocation admission or live proof-recording transaction."""

    def __init__(
        self,
        transaction_manager: TransactionManager,
        job_store: JobStore,
        admitted_work_authorizer: AdmittedWorkAuthorizer,
        artifact_cleanup_authorizer: ArtifactCleanupAuthorizer,
    ) -> None:
        self._transaction_manager = transaction_manager
        self._job_store = job_store
        self._admitted_work_authorizer = admitted_work_authorizer
        self._artifact_cleanup_authorizer = artifact_cleanup_authorizer

    async def register(self, binding: JobEffectBindingDTO) -> None:
        async with self._transaction_manager.begin():
            await self._guard(binding)
            await self._job_store.register_effect(binding)

    @override
    async def admit_put(self, observation: JobEffectId, attempt: ArtifactAttemptDTO) -> None:
        async with self._transaction_manager.begin():
            stored = await self._load(
                observation, JobEffectAction.PUT, attempt.scope, attempt.attempt_id
            )
            if (stored.binding.artifact_id, stored.binding.length, stored.binding.digest) != (
                attempt.artifact_id,
                attempt.length,
                attempt.digest,
            ):
                raise ConflictError("The sealed PUT expectation differs from the original.")
            await self._admit(stored)

    @override
    async def admit_delete(
        self, observation: JobEffectId, scope: ArtifactScopeDTO, attempt_id: ArtifactAttemptId
    ) -> None:
        async with self._transaction_manager.begin():
            stored = await self._load(observation, JobEffectAction.DELETE, scope, attempt_id)
            await self._admit(stored)

    @override
    async def record_put_abort(self, observation: JobEffectId, attempt: ArtifactAttemptDTO) -> None:
        async with self._transaction_manager.begin():
            stored = await self._load(
                observation, JobEffectAction.PUT, attempt.scope, attempt.attempt_id
            )
            if (stored.binding.artifact_id, stored.binding.length, stored.binding.digest) != (
                attempt.artifact_id,
                attempt.length,
                attempt.digest,
            ):
                raise ConflictError("The sealed PUT expectation differs from the original.")
            await self._record(stored)

    @override
    async def record_delete_abort(
        self, observation: JobEffectId, scope: ArtifactScopeDTO, attempt_id: ArtifactAttemptId
    ) -> None:
        async with self._transaction_manager.begin():
            stored = await self._load(observation, JobEffectAction.DELETE, scope, attempt_id)
            await self._record(stored)

    async def _load(
        self,
        effect_id: JobEffectId,
        action: JobEffectAction,
        scope: ArtifactScopeDTO,
        attempt_id: ArtifactAttemptId,
    ) -> JobEffectObservationDTO:
        """Require the exact original invocation before admitting or recording its observation."""
        stored = await self._job_store.effect(effect_id)
        if stored is None or (
            stored.binding.effect_id,
            stored.binding.action,
            stored.binding.scope,
            stored.binding.artifact_attempt_id,
        ) != (effect_id, action, scope, attempt_id):
            raise ConflictError("The original physical invocation cannot be confirmed.")
        return stored

    async def _admit(self, stored: JobEffectObservationDTO) -> None:
        """Authorize one previously unadmitted physical invocation without replaying its admission."""
        if (
            stored.admitted_at is not None
            or stored.kind is not None
            or stored.consumed_at is not None
        ):
            raise ConflictError("Physical invocation admission cannot be replayed.")
        await self._guard(stored.binding)
        await self._job_store.admit_effect(stored)

    async def _record(self, stored: JobEffectObservationDTO) -> None:
        """Record only an admitted, unconsumed invocation after checking current ownership."""
        if stored.admitted_at is None or stored.consumed_at is not None:
            raise ConflictError("The original invocation has no live recording admission.")
        await self._guard(stored.binding)
        await self._job_store.record_effect_abort(stored)

    async def _guard(self, binding: JobEffectBindingDTO) -> None:
        """Recheck the original artifact scope, current authority and fenced job ownership."""
        if (
            not binding.unit
            or len(binding.unit) > 100
            or ((binding.length is None) != (binding.digest is None))
            or (binding.action == JobEffectAction.PUT and binding.length is None)
        ):
            raise ConflictError("The original artifact expectation is incomplete.")
        context = binding.context
        if isinstance(context.binding, ProductJobBindingDTO):
            authority = context.binding.authority
            if (authority.installation_id, authority.organization_id, authority.project_id) != (
                binding.scope.installation_id,
                binding.scope.organization_id,
                binding.scope.project_id,
            ):
                raise ConflictError("The artifact is outside the admitted product scope.")
            await self._admitted_work_authorizer.require_current(authority)
        current = await self._job_store.require_current(context)
        if current.pending_effect not in (None, binding.unit):
            raise ConflictError("Another original effect is unresolved.")
        if isinstance(context.binding, ArtifactCleanupJobBindingDTO):
            facts = await self._artifact_cleanup_authorizer.require_current(
                context.job_id, context.binding
            )
            if (
                facts.binding != context.binding
                or facts.job_id != context.job_id
                or (
                    context.binding.scope != binding.scope
                    or binding.artifact_attempt_id not in facts.targets
                )
            ):
                raise ConflictError("The artifact is outside the original cleanup obligation.")
        elif current.cancel_requested:
            raise JobStoppedError("The original product work was canceled.")
        await self._job_store.validate_effect_target(binding)
