import asyncio
from typing import override

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.domain.policies.principal_access_policy import PrincipalAccessPolicy
from inframeld_backend.access.domain.policies.project_visibility_policy import (
    ProjectVisibilityPolicy,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.indexing.application.dtos.embedding_profile_dto import EmbeddingProfileDTO
from inframeld_backend.indexing.application.dtos.embedding_profile_page_dto import (
    EmbeddingProfilePageDTO,
)
from inframeld_backend.indexing.application.protocols.embedding_profile_read_repository import (
    EmbeddingProfileReadRepository,
)
from inframeld_backend.indexing.application.protocols.embedding_profile_reader import (
    EmbeddingProfileReader,
)
from inframeld_backend.indexing.application.value_objects.embedding_profiles_cursor import (
    EmbeddingProfilesCursor,
)
from inframeld_backend.indexing.domain.value_objects.embedding_profile_id import (
    EmbeddingProfileId,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
    InvalidInputError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

_INVALID_CURSOR = "The continuation cursor is invalid or incompatible."


class EmbeddingProfileReadService(EmbeddingProfileReader):
    """Read saved definitions under current exact View assignments."""

    def __init__(
        self, transactions: TransactionManager, repository: EmbeddingProfileReadRepository
    ) -> None:
        self._transactions = transactions
        self._repository = repository

    @override
    async def get(
        self, access: AccessContextDTO, project_id: ProjectId, profile_id: EmbeddingProfileId
    ) -> EmbeddingProfileDTO:
        try:
            async with asyncio.timeout(5), self._transactions.begin():
                _, facts = await self._require_scope(access, project_id)
                profile = await self._repository.get_visible(facts, project_id, profile_id)
                if profile is None:
                    raise ResourceNotFoundError()
                if profile.layout.embedding_profile_id != profile_id:
                    raise RuntimeError("Embedding Profile observation changed the exact target.")
                self._require_profile_scope(profile, facts, project_id)
                return profile
        except TimeoutError:
            raise DependencyUnavailableError() from None

    @override
    async def list_profiles(
        self, access: AccessContextDTO, project_id: ProjectId, limit: int, cursor: str | None
    ) -> EmbeddingProfilePageDTO:
        if not 1 <= limit <= 100:
            raise InvalidInputError()
        try:
            async with asyncio.timeout(5), self._transactions.begin():
                installation, facts = await self._require_scope(access, project_id)
                try:
                    position = (
                        EmbeddingProfilesCursor.from_token(cursor) if cursor is not None else None
                    )
                except ValueError:
                    raise InvalidInputError(_INVALID_CURSOR) from None
                if position is not None and (position.installation_id, position.project_id) != (
                    installation,
                    project_id,
                ):
                    raise InvalidInputError(_INVALID_CURSOR)

                after = position.after if position is not None else None
                rows = await self._repository.list_visible(facts, project_id, after, limit + 1)
                if len(rows) > limit + 1:
                    raise RuntimeError("Embedding Profile observation exceeded its page bound.")
                for row in rows:
                    self._require_profile_scope(row, facts, project_id)
                    profile_id = row.layout.embedding_profile_id
                    if after is not None and profile_id.value <= after.value:
                        raise RuntimeError("Embedding Profile observation changed its position.")
                    after = profile_id

                items = rows[:limit]
                next_cursor = (
                    EmbeddingProfilesCursor(
                        installation, project_id, items[-1].layout.embedding_profile_id
                    ).to_token()
                    if len(rows) > limit
                    else None
                )
                return EmbeddingProfilePageDTO(items, next_cursor)
        except TimeoutError:
            raise DependencyUnavailableError() from None

    async def _require_scope(
        self, access: AccessContextDTO, project_id: ProjectId
    ) -> tuple[InstallationId, ProjectActionFactsDTO]:
        scope = await self._repository.lock_scope(access, project_id)
        if scope is None:
            raise ResourceNotFoundError()
        _, facts = scope
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
        return scope

    @staticmethod
    def _require_profile_scope(
        profile: EmbeddingProfileDTO, facts: ProjectActionFactsDTO, project_id: ProjectId
    ) -> None:
        if (profile.layout.organization_id, profile.layout.project_id) != (
            facts.principal.organization_id,
            project_id,
        ):
            raise RuntimeError("Embedding Profile observation changed the exact target.")
        if not profile.has_coherent_layout():
            raise RuntimeError("Embedding Profile observation has incoherent shard references.")
