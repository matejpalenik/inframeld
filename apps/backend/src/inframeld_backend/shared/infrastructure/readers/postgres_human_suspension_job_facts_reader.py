from typing import override
from uuid import UUID

from sqlalchemy import DateTime, and_, exists, func, select
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.infrastructure.resources.postgres_identity_coordinator import (
    PostgresIdentityCoordinator,
)
from inframeld_backend.access.infrastructure.rows.host_maintenance_receipt_row import (
    HostMaintenanceReceiptRow,
)
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.shared.application.dtos.human_suspension_job_binding_dto import (
    HumanSuspensionJobBindingDTO,
)
from inframeld_backend.shared.application.dtos.human_suspension_job_facts_dto import (
    HumanSuspensionJobFactsDTO,
)
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.enums.human_suspension_cleanup_step import (
    HumanSuspensionCleanupStep,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.protocols.human_suspension_job_facts_reader import (
    HumanSuspensionJobFactsReader,
)
from inframeld_backend.shared.application.value_objects.job_payload import JobPayload
from inframeld_backend.shared.domain.enums.job_status import JobStatus
from inframeld_backend.shared.infrastructure.mappers.postgres_job_binding_mapper import (
    PostgresJobBindingMapper,
)
from inframeld_backend.shared.infrastructure.rows.durable_job_attempt_row import (
    DurableJobAttemptRow,
)
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow
from inframeld_backend.shared.infrastructure.rows.human_suspension_obligation_row import (
    HumanSuspensionObligationRow,
)
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class PostgresHumanSuspensionJobFactsReader(HumanSuspensionJobFactsReader):
    """Read the suspended target and live attempt under the existing ownership locks."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def read_live_attempt(
        self, context: JobAttemptContextDTO, *, worker_id: UUID
    ) -> HumanSuspensionJobFactsDTO | None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Suspension attempt facts require the active caller transaction.")
        binding = context.binding
        if (
            not isinstance(binding, HumanSuspensionJobBindingDTO)
            or context.job_id != binding.job_id
            or type(context.attempt) is not int
            or not 1 <= context.attempt <= 3
        ):
            return None
        payload = JobPayload("human.suspension-cleanup", 1, binding.obligation_id.value.bytes)
        if context.payload != payload:
            return None
        try:
            with self._session.no_autoflush:
                return await self._read_locked(context, binding, worker_id, payload)
        except (OperationalError, InterfaceError, SqlAlchemyTimeoutError) as error:
            raise DependencyUnavailableError() from error

    async def _read_locked(
        self,
        context: JobAttemptContextDTO,
        binding: HumanSuspensionJobBindingDTO,
        worker_id: UUID,
        payload: JobPayload,
    ) -> HumanSuspensionJobFactsDTO | None:
        parent = await self.lock_original(binding)
        if parent is None:
            return None
        job = await self.lock_child(parent)
        if (
            job is None
            or job.status != JobStatus.RUNNING.value
            or job.cancel_requested
            or (
                job.attempt_count,
                job.worker_id,
                job.fence,
                job.work_deadline,
            )
            != (
                context.attempt,
                worker_id,
                context.fence.value,
                context.work_deadline,
            )
            or job.lease_expires_at is None
            or job.work_deadline is None
        ):
            return None
        attempt = await self.lock_open_attempt(job)
        if attempt is None or not await self.has_current_target(binding):
            return None
        now = await self._session.scalar(
            select(func.clock_timestamp(type_=DateTime(timezone=True)))
        )
        if now is None:
            raise DependencyUnavailableError("The authoritative database clock is unavailable.")
        if not attempt.started_at <= now < job.lease_expires_at <= job.work_deadline:
            return None
        return HumanSuspensionJobFactsDTO(
            binding=binding,
            payload=payload,
            attempt=attempt.number,
            fence=context.fence,
            worker_id=attempt.worker_id,
            work_deadline=job.work_deadline,
            lease_expires_at=job.lease_expires_at,
            observed_at=now,
            source_revision=parent.source_revision,
        )

    async def lock_original(
        self, binding: HumanSuspensionJobBindingDTO
    ) -> HumanSuspensionObligationRow | None:
        """Lock the exact unfinished original for live work."""
        parent = await self.lock_retained_original(binding)
        if (
            parent is None
            or parent.completed_at is not None
            or parent.queue_exhausted_at is not None
        ):
            return None
        return parent

    async def lock_retained_original(
        self, binding: HumanSuspensionJobBindingDTO
    ) -> HumanSuspensionObligationRow | None:
        """Verify the retained identity before taking identity, Organization and parent turns."""
        original_id = binding.obligation_id.value
        original = await self._session.get(
            HumanSuspensionObligationRow, original_id, populate_existing=True
        )
        if original is None or PostgresJobBindingMapper.human_suspension(original) != binding:
            return None
        await PostgresIdentityCoordinator(self._session).acquire(
            installation_id=binding.installation_id, identity=binding.identity
        )
        organization = await self._session.scalar(
            select(OrganizationRow.id)
            .where(OrganizationRow.id == binding.organization_id)
            .with_for_update()
        )
        if organization is None:
            return None
        parent = await self._session.get(
            HumanSuspensionObligationRow, original_id, populate_existing=True, with_for_update=True
        )
        if parent is None or PostgresJobBindingMapper.human_suspension(parent) != binding:
            return None
        return parent

    async def lock_child(self, parent: HumanSuspensionObligationRow) -> DurableJobRow | None:
        """Match the exact child, payload and original times under the parent's lock."""
        child = await self._session.get(
            DurableJobRow, parent.job_id, populate_existing=True, with_for_update=True
        )
        if child is None or not self.matches_child(parent, child):
            return None
        return child

    @staticmethod
    def matches_child(parent: HumanSuspensionObligationRow, child: DurableJobRow) -> bool:
        return (
            child.binding_kind,
            child.suspension_obligation_id,
            child.installation_id,
            child.organization_id,
            child.request_id,
            child.admitted_at,
            child.queued_deadline,
            child.payload_kind,
            child.payload_version,
            child.payload,
        ) == (
            "human_suspension",
            parent.id,
            parent.installation_id,
            parent.organization_id,
            parent.request_id,
            parent.admitted_at,
            parent.queued_deadline,
            "human.suspension-cleanup",
            1,
            parent.id.bytes,
        )

    async def lock_open_attempt(self, job: DurableJobRow) -> DurableJobAttemptRow | None:
        """Read the currently fenced attempt under the exact child lock."""
        attempt = await self._session.get(
            DurableJobAttemptRow,
            (job.id, job.attempt_count),
            populate_existing=True,
            with_for_update=True,
        )
        if (
            attempt is None
            or attempt.ended_at is not None
            or attempt.worker_id != job.worker_id
            or attempt.fence != job.fence
            or not job.admitted_at <= attempt.started_at < job.queued_deadline
        ):
            return None
        return attempt

    @staticmethod
    def decode_marker(job: DurableJobRow) -> tuple[HumanSuspensionCleanupStep, int, UUID] | None:
        """Decode a canonical stored marker without establishing dispatch authority."""
        if job.pending_effect is None:
            return None
        try:
            step_text, number_text, fence_text = job.pending_effect.split(":")
            step = HumanSuspensionCleanupStep(step_text)
            number, fence = int(number_text), UUID(fence_text)
        except ValueError:
            return None
        if (
            not 1 <= number <= min(job.attempt_count, 3)
            or job.pending_effect != f"{step.value}:{number}:{fence}"
        ):
            return None
        return step, number, fence

    async def lock_ended_marker(
        self, job: DurableJobRow
    ) -> tuple[HumanSuspensionCleanupStep, DurableJobAttemptRow] | None:
        """Match the unresolved marker to its actual ended attempt under the child lock."""
        marker = self.decode_marker(job)
        if marker is None or job.work_deadline is None:
            return None
        step, number, fence = marker
        attempt = await self._session.get(
            DurableJobAttemptRow, (job.id, number), populate_existing=True, with_for_update=True
        )
        if (
            attempt is None
            or attempt.fence != fence
            or attempt.ended_at is None
            or not job.admitted_at <= attempt.started_at < job.queued_deadline
            or not attempt.started_at < job.work_deadline
            or attempt.ended_at < attempt.started_at
        ):
            return None
        return step, attempt

    async def lock_unused_repeat(
        self, parent: HumanSuspensionObligationRow, job: DurableJobRow
    ) -> tuple[HostMaintenanceReceiptRow, HumanSuspensionCleanupStep, DurableJobAttemptRow] | None:
        """Match the single unused repeat to the exact original and earlier marker."""
        marker = await self.lock_ended_marker(job)
        if marker is None:
            return None
        step, attempt = marker
        if self.step_states(parent)[step] is IdentityRecoveryCleanupState.CONFIRMED:
            return None
        r = HostMaintenanceReceiptRow
        receipt = await self._session.scalar(
            select(r)
            .where(
                r.installation_id == parent.installation_id,
                r.suspension_obligation_id == parent.id,
                r.authority == parent.authority,
                r.subject == parent.subject,
                r.mode == "human-suspension-cleanup",
                r.outcome == "requeued",
                r.suspension_repeat_step == step.value,
                r.suspension_repeat_attempt == attempt.number,
                r.suspension_repeat_fence == attempt.fence,
                r.suspension_repeat_consumed_at.is_(None),
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if receipt is None or attempt.ended_at is None or receipt.authorized_at < attempt.ended_at:
            return None
        return receipt, step, attempt

    @staticmethod
    def step_states(
        parent: HumanSuspensionObligationRow,
    ) -> dict[HumanSuspensionCleanupStep, IdentityRecoveryCleanupState]:
        return {
            HumanSuspensionCleanupStep.KRATOS_SESSIONS: parent.kratos_sessions,
            HumanSuspensionCleanupStep.HYDRA_CLI_GRANTS: parent.hydra_cli_grants,
            HumanSuspensionCleanupStep.HYDRA_REMEMBERED_LOGINS: parent.hydra_remembered_logins,
        }

    async def has_current_target(
        self, binding: HumanSuspensionJobBindingDTO, *, allow_restored: bool = False
    ) -> bool:
        """Read current target status and linkage under its original identity turn."""
        parent = HumanSuspensionObligationRow
        # Organization Access revisions determine suspension order even when clocks tie.
        superseded = exists().where(
            parent.id != binding.obligation_id.value,
            parent.installation_id == binding.installation_id.value,
            parent.organization_id == binding.organization_id,
            parent.principal_id == binding.principal_id,
            parent.access_revision >= binding.access_revision,
        )
        installed = exists().where(
            InstallationIdentityRow.singleton_key == 1,
            InstallationIdentityRow.installation_id == binding.installation_id.value,
        )
        statuses = (
            (PrincipalStatus.SUSPENDED, PrincipalStatus.ACTIVE)
            if allow_restored
            else (PrincipalStatus.SUSPENDED,)
        )
        current = await self._session.scalar(
            select(PrincipalRow.id)
            .join(OrganizationRow, OrganizationRow.id == PrincipalRow.organization_id)
            .join(
                HumanIdentityLinkRow,
                and_(
                    HumanIdentityLinkRow.principal_id == PrincipalRow.id,
                    HumanIdentityLinkRow.organization_id == PrincipalRow.organization_id,
                    HumanIdentityLinkRow.principal_kind == PrincipalRow.kind,
                ),
            )
            .where(
                PrincipalRow.id == binding.principal_id,
                OrganizationRow.id == binding.organization_id,
                OrganizationRow.access_revision >= binding.access_revision,
                PrincipalRow.kind == PrincipalKind.HUMAN,
                PrincipalRow.status.in_(statuses),
                HumanIdentityLinkRow.authority == binding.identity.authority.value,
                HumanIdentityLinkRow.subject == binding.identity.subject.value,
                installed,
                ~superseded,
            )
        )
        return current == binding.principal_id
