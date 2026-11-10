from dataclasses import replace
from typing import override

import pytest
from tests.support.job_effect_recovery_handler import (
    MockEffectCleanupAuthority,
    MockEffectStore,
    MockEffectTransactions,
    original_effect,
)

from inframeld_backend.shared.application.dtos.artifact_cleanup_job_binding_dto import (
    ArtifactCleanupJobBindingDTO,
)
from inframeld_backend.shared.application.dtos.artifact_cleanup_target_dto import (
    ArtifactCleanupTargetDTO,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
)
from inframeld_backend.shared.application.errors.job_errors import JobFenceLostError
from inframeld_backend.shared.application.protocols.artifact_cleanup_target_reader import (
    ArtifactCleanupTargetReader,
)
from inframeld_backend.shared.application.services.artifact_local_cleanup_service import (
    ArtifactLocalCleanupService,
)
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.artifact_content_digest import (
    ArtifactContentDigest,
)
from inframeld_backend.shared.application.value_objects.job_payload import JobPayload
from inframeld_backend.shared.infrastructure.repositories.postgres_artifact_attempt_repository import (
    PostgresArtifactAttemptRepository,
)


class MockLocalAttempts(PostgresArtifactAttemptRepository):
    """Override the only two transitions this unit exercises, without executing SQL."""

    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.needs_removal = True

    @override
    async def retire_local(
        self, binding: ArtifactCleanupJobBindingDTO, target: ArtifactCleanupTargetDTO
    ) -> bool:
        self.events.append("retired")
        assert target.length is None and target.digest is None
        return self.needs_removal

    @override
    async def confirm_local_removed(
        self, binding: ArtifactCleanupJobBindingDTO, target: ArtifactCleanupTargetDTO
    ) -> None:
        self.events.append("local_settled")


class MockTargets(ArtifactCleanupTargetReader):
    def __init__(self, jobs: MockEffectStore, malformed: bool = False) -> None:
        self.jobs = jobs
        self.malformed = malformed

    @override
    async def read(
        self, binding: ArtifactCleanupJobBindingDTO, attempt_id: ArtifactAttemptId
    ) -> ArtifactCleanupTargetDTO | None:
        self.jobs.events.append("target")
        source = self.jobs.binding
        return ArtifactCleanupTargetDTO(
            source.artifact_id,
            source.artifact_attempt_id,
            source.scope,
            -1 if self.malformed else None,
            ArtifactContentDigest.from_content(b"") if self.malformed else None,
        )


def _operation(
    *, malformed: bool = False
) -> tuple[
    ArtifactLocalCleanupService, MockEffectStore, MockEffectCleanupAuthority, MockLocalAttempts
]:
    effect = original_effect()
    binding = effect.context.binding
    assert isinstance(binding, ArtifactCleanupJobBindingDTO)
    effect = replace(
        effect,
        context=replace(
            effect.context,
            payload=JobPayload("artifact.cleanup", 1, binding.obligation_id.value.bytes),
        ),
    )
    jobs = MockEffectStore(effect)
    authority = MockEffectCleanupAuthority(jobs)
    authority.facts = replace(authority.facts, retention_allows_cleanup=True, pending_write=True)
    attempts = MockLocalAttempts(jobs.events)
    return (
        ArtifactLocalCleanupService(
            MockEffectTransactions(jobs.events),
            jobs,
            authority,
            MockTargets(jobs, malformed),
            attempts,
        ),
        jobs,
        authority,
        attempts,
    )


@pytest.mark.asyncio
async def test_local_retirement_and_confirmation_do_not_clear_remote_pending_write() -> None:
    service, jobs, authority, _ = _operation()
    target = await service.prepare_local(jobs.binding.context)
    assert target is not None and target.length is None and target.digest is None
    assert jobs.events == ["begin", "fence", "cleanup", "target", "retired", "commit"]
    await service.confirm_local(jobs.binding.context, target)
    assert jobs.events[-2:] == ["local_settled", "commit"]
    assert authority.facts.pending_write and not authority.facts.physically_complete


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["fence", "published"])
async def test_lost_fence_or_published_target_prevents_local_retirement(reason: str) -> None:
    service, jobs, authority, _ = _operation()
    if reason == "fence":
        jobs.fence_error = True
    else:
        authority.facts = replace(authority.facts, published=True)
    with pytest.raises((JobFenceLostError, AccessDeniedError)):
        await service.prepare_local(jobs.binding.context)
    assert "retired" not in jobs.events


@pytest.mark.asyncio
async def test_invalid_saved_length_is_rejected_before_local_retirement() -> None:
    service, jobs, _, _ = _operation(malformed=True)
    with pytest.raises(ConflictError):
        await service.prepare_local(jobs.binding.context)
    assert "retired" not in jobs.events
