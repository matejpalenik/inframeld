from dataclasses import replace
from typing import override
from uuid import UUID

import pytest

from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.artifact_cleanup_facts_dto import (
    ArtifactCleanupFactsDTO,
)
from inframeld_backend.shared.application.dtos.artifact_cleanup_job_binding_dto import (
    ArtifactCleanupJobBindingDTO,
)
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.dtos.unadmitted_staging_artifact_origin_dto import (
    UnadmittedStagingArtifactOriginDTO,
)
from inframeld_backend.shared.application.enums.artifact_cleanup_kind import ArtifactCleanupKind
from inframeld_backend.shared.application.errors.application_errors import AccessDeniedError
from inframeld_backend.shared.application.protocols.artifact_cleanup_facts_reader import (
    ArtifactCleanupFactsReader,
)
from inframeld_backend.shared.application.services.artifact_cleanup_authorization_service import (
    ArtifactCleanupAuthorizationService,
)
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.artifact_cleanup_obligation_id import (
    ArtifactCleanupObligationId,
)
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

SCOPE = ArtifactScopeDTO(
    InstallationId(UUID(int=1)), OrganizationId(UUID(int=2)), ProjectId(UUID(int=3))
)
ATTEMPT = ArtifactAttemptId(UUID(int=4))
JOB = JobId(UUID(int=5))
BINDING = ArtifactCleanupJobBindingDTO(
    ArtifactCleanupObligationId(UUID(int=6)),
    SCOPE,
    ArtifactCleanupKind.ABANDONED_STAGING,
    UnadmittedStagingArtifactOriginDTO(ATTEMPT, RequestId(UUID(int=7))),
)
FACTS = ArtifactCleanupFactsDTO(
    binding=BINDING,
    job_id=JOB,
    targets=(ATTEMPT,),
    owns_targets=True,
    retirement_authorized=False,
    retention_allows_cleanup=False,
    published=False,
    pending_write=False,
)


class MockCleanupFactsReader(ArtifactCleanupFactsReader):
    def __init__(self, facts: ArtifactCleanupFactsDTO | None) -> None:
        self.facts = facts

    @override
    async def read(
        self, obligation_id: ArtifactCleanupObligationId
    ) -> ArtifactCleanupFactsDTO | None:
        return self.facts


@pytest.mark.asyncio
async def test_original_owned_stage_cleanup_needs_no_current_product_principal() -> None:
    # Original ownership survives account suspension, grant loss and Project blocking.
    result = await ArtifactCleanupAuthorizationService(
        MockCleanupFactsReader(FACTS)
    ).require_current(JOB, BINDING)
    assert result == FACTS


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "facts", [None, replace(FACTS, owns_targets=False), replace(FACTS, targets=())]
)
async def test_missing_or_unowned_obligation_cannot_authorize_cleanup(
    facts: ArtifactCleanupFactsDTO | None,
) -> None:
    with pytest.raises(AccessDeniedError):
        await ArtifactCleanupAuthorizationService(MockCleanupFactsReader(facts)).require_current(
            JOB, BINDING
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "binding",
    [
        replace(BINDING, obligation_id=ArtifactCleanupObligationId(UUID(int=8))),
        replace(BINDING, scope=replace(SCOPE, project_id=ProjectId(UUID(int=8)))),
        replace(BINDING, kind=ArtifactCleanupKind.ERASURE),
        replace(BINDING, origin=replace(BINDING.origin, request_id=RequestId(UUID(int=8)))),
    ],
)
async def test_changed_obligation_meaning_cannot_borrow_existing_authority(
    binding: ArtifactCleanupJobBindingDTO,
) -> None:
    with pytest.raises(AccessDeniedError):
        await ArtifactCleanupAuthorizationService(MockCleanupFactsReader(FACTS)).require_current(
            JOB, binding
        )


@pytest.mark.asyncio
async def test_other_job_cannot_borrow_original_obligation() -> None:
    with pytest.raises(AccessDeniedError):
        await ArtifactCleanupAuthorizationService(MockCleanupFactsReader(FACTS)).require_current(
            JobId(UUID(int=8)), BINDING
        )


@pytest.mark.asyncio
async def test_unadmitted_origin_must_identify_the_exact_owned_attempt() -> None:
    binding = replace(
        BINDING,
        origin=UnadmittedStagingArtifactOriginDTO(
            ArtifactAttemptId(UUID(int=9)), BINDING.origin.request_id
        ),
    )
    with pytest.raises(AccessDeniedError):
        await ArtifactCleanupAuthorizationService(
            MockCleanupFactsReader(replace(FACTS, binding=binding))
        ).require_current(JOB, binding)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind", [ArtifactCleanupKind.ERASURE, ArtifactCleanupKind.RETENTION_EXPIRY]
)
async def test_erasure_or_expiry_requires_persisted_retirement(kind: ArtifactCleanupKind) -> None:
    binding = replace(BINDING, kind=kind)
    with pytest.raises(AccessDeniedError):
        await ArtifactCleanupAuthorizationService(
            MockCleanupFactsReader(replace(FACTS, binding=binding))
        ).require_current(JOB, binding)


@pytest.mark.asyncio
async def test_ordinary_expiry_cannot_override_protected_retention() -> None:
    binding = replace(BINDING, kind=ArtifactCleanupKind.RETENTION_EXPIRY)
    facts = replace(FACTS, binding=binding, retirement_authorized=True)
    with pytest.raises(AccessDeniedError):
        await ArtifactCleanupAuthorizationService(MockCleanupFactsReader(facts)).require_current(
            JOB, binding
        )


@pytest.mark.asyncio
async def test_explicit_erasure_preserves_accepted_retention_override() -> None:
    binding = replace(BINDING, kind=ArtifactCleanupKind.ERASURE)
    facts = replace(FACTS, binding=binding, retirement_authorized=True)
    assert (
        await ArtifactCleanupAuthorizationService(MockCleanupFactsReader(facts)).require_current(
            JOB, binding
        )
        == facts
    )


@pytest.mark.asyncio
async def test_published_or_unknown_write_facts_survive_staging_authorization() -> None:
    facts = replace(FACTS, published=True, pending_write=True)
    result = await ArtifactCleanupAuthorizationService(
        MockCleanupFactsReader(facts)
    ).require_current(JOB, BINDING)
    assert result.published and result.pending_write
