import asyncio

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.domain.policies.principal_access_policy import PrincipalAccessPolicy
from inframeld_backend.access.domain.policies.project_visibility_policy import (
    ProjectVisibilityPolicy,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.indexing.application.dtos.embedding_profile_dto import EmbeddingProfileDTO
from inframeld_backend.indexing.application.protocols.embedding_profile_read_repository import (
    EmbeddingProfileReadRepository,
)
from inframeld_backend.indexing.domain.value_objects.embedding_profile_id import EmbeddingProfileId
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager


class EmbeddingProfileReadService:
    """Read one saved definition under the caller's current exact View assignment."""

    def __init__(
        self, transactions: TransactionManager, repository: EmbeddingProfileReadRepository
    ) -> None:
        self._transactions = transactions
        self._repository = repository

    async def get(
        self, access: AccessContextDTO, project_id: ProjectId, profile_id: EmbeddingProfileId
    ) -> EmbeddingProfileDTO:
        try:
            async with asyncio.timeout(5), self._transactions.begin():
                facts = await self._repository.lock_scope(access, project_id)
                if facts is None:
                    raise ResourceNotFoundError()
                if facts.principal.id != access.actor_principal_id:
                    raise RuntimeError("Embedding Profile observation changed the actor.")

                eligibility = PrincipalAccessEvaluationService.evaluate(
                    access=access,
                    principal=facts.principal,
                    has_pending_recovery=facts.has_pending_recovery,
                    oauth_credential_facts=facts.oauth_credential_facts,
                    application_key_facts=facts.application_key_facts,
                )
                PrincipalAccessEvaluationService.require_current_credential(
                    access=access, principal_access=eligibility
                )
                if not (
                    PrincipalAccessPolicy.may_use_product(eligibility)
                    and ProjectVisibilityPolicy.may_view_project(
                        principal_status=facts.principal.status,
                        project_status=facts.project_status,
                        is_project_member=facts.is_project_member,
                    )
                ):
                    raise ResourceNotFoundError()

                profile = await self._repository.get_visible(facts, project_id, profile_id)
                if profile is None:
                    raise ResourceNotFoundError()
                layout = profile.layout
                if (
                    layout.organization_id != facts.principal.organization_id
                    or layout.project_id != project_id
                    or layout.embedding_profile_id != profile_id
                ):
                    raise RuntimeError("Embedding Profile observation changed the exact target.")
                if not profile.has_coherent_layout():
                    raise RuntimeError(
                        "Embedding Profile observation has incoherent shard references."
                    )
                return profile
        except TimeoutError:
            raise DependencyUnavailableError() from None
