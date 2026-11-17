from dataclasses import replace
from typing import Literal, override
from uuid import UUID

import pytest
from tests.support.mock_project_metadata import (
    ACCESS,
    NEW_RESERVATION,
    ORGANIZATION_ID,
    PROJECT_ID,
    SAVED_RESULT,
    MockOperationIdempotency,
    MockTransactions,
)

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_key_authentication_dto import (
    ApplicationKeyAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.human_credential_facts_dto import (
    HumanCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.model_connection_access_dto import (
    ModelConnectionAccessDTO,
)
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.model_connection_authentication import (
    ModelConnectionAuthentication,
)
from inframeld_backend.access.domain.enums.model_connection_provider import ModelConnectionProvider
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.policies.model_connection_destination_policy import (
    ModelConnectionDestinationPolicy,
)
from inframeld_backend.access.domain.value_objects.application_key_id import ApplicationKeyId
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.indexing.application.commands.create_embedding_profile_command import (
    CreateEmbeddingProfileCommand,
)
from inframeld_backend.indexing.application.dtos.embedding_profile_creation_dto import (
    EmbeddingProfileCreationDTO,
)
from inframeld_backend.indexing.application.dtos.embedding_profile_creation_facts_dto import (
    EmbeddingProfileCreationFactsDTO,
)
from inframeld_backend.indexing.application.dtos.embedding_profile_dto import EmbeddingProfileDTO
from inframeld_backend.indexing.application.protocols.embedding_profile_creation_repository import (
    EmbeddingProfileCreationRepository,
)
from inframeld_backend.indexing.application.services.embedding_profile_creation_service import (
    EmbeddingProfileCreationService,
)
from inframeld_backend.indexing.domain.enums.embedding_profile_action import EmbeddingProfileAction
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.effective_model_settings_dto import (
    EffectiveModelSettingsDTO,
)
from inframeld_backend.shared.application.dtos.embedding_model_settings_dto import (
    EmbeddingModelSettingsDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.dtos.model_selection_dto import ModelSelectionDTO
from inframeld_backend.shared.application.dtos.model_token_bound_dto import ModelTokenBoundDTO
from inframeld_backend.shared.application.enums.embedding_distance import EmbeddingDistance
from inframeld_backend.shared.application.enums.embedding_normalization import (
    EmbeddingNormalization,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.model_role import ModelRole
from inframeld_backend.shared.application.enums.model_token_bound_kind import ModelTokenBoundKind
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    DependencyUnavailableError,
    InvalidInputError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)

_SETTINGS = EmbeddingModelSettingsDTO(
    dimensions=1536,
    normalization=EmbeddingNormalization.L2,
    distance=EmbeddingDistance.COSINE,
    document_prefix="passage: ",
    query_prefix="query: ",
    expected_provider="openai",
    expected_model_revision="2026-07-01",
    role=ModelRole.EMBEDDING,
)
_COMMAND = CreateEmbeddingProfileCommand(
    project_id=PROJECT_ID,
    name=ResourceName("support-embeddings"),
    display_name=SubmittedDisplayName("Support embeddings"),
    selection=ModelSelectionDTO(
        PROJECT_ID, ModelConnectionId(UUID(int=4)), "ExactModel-v1", ModelRole.EMBEDDING
    ),
    effective=EffectiveModelSettingsDTO(
        8192,
        ModelTokenBoundDTO(ModelTokenBoundKind.EXACT, "fixture-tokenizer", "fixture-revision"),
        _SETTINGS,
    ),
)
_CONTEXT = IdempotencyContextDTO(
    HttpMethod.POST,
    f"/v1/projects/{PROJECT_ID.value}/embedding-profiles",
    IdempotencyKey("embedding-profile-create"),
)
_FACTS = EmbeddingProfileCreationFactsDTO(
    organization_id=ORGANIZATION_ID,
    project_id=PROJECT_ID,
    access_revision=7,
    action=ProjectActionFactsDTO(
        Principal(
            ACCESS.actor_principal_id, ORGANIZATION_ID, PrincipalKind.HUMAN, PrincipalStatus.ACTIVE
        ),
        False,
        HumanCredentialFactsDTO(True, HumanCredentialVersion(1)),
        ProjectStatus.ACTIVE,
        True,
        True,
    ),
)


class MockEmbeddingProfileCreationRepository(EmbeddingProfileCreationRepository):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.facts = _FACTS
        self.live_connection: ModelConnectionAccessDTO | None = ModelConnectionAccessDTO(
            ModelConnectionProvider.OPENAI,
            "https://api.openai.com/v1",
            None,
            ModelConnectionAuthentication.API_KEY,
        )
        self.saved: EmbeddingProfileCreationDTO | None = None

    @override
    async def lock_for_creation(
        self, *, access: AccessContextDTO, project_id: ProjectId
    ) -> EmbeddingProfileCreationFactsDTO:
        assert self.events == ["begin"]
        assert access.actor_principal_id == ACCESS.actor_principal_id and project_id == PROJECT_ID
        self.events.append("authority")
        return self.facts

    @override
    async def lock_live_selection(
        self, *, facts: EmbeddingProfileCreationFactsDTO, connection_id: ModelConnectionId
    ) -> ModelConnectionAccessDTO | None:
        assert facts == self.facts and connection_id == _COMMAND.selection.connection_id
        self.events.append("selection")
        return self.live_connection

    @override
    async def original(
        self,
        *,
        access: AccessContextDTO,
        facts: EmbeddingProfileCreationFactsDTO,
        operation: CompletedSynchronousOperationDTO,
    ) -> EmbeddingProfileCreationDTO:
        assert access == ACCESS and facts == self.facts and operation == SAVED_RESULT
        self.events.append("original")
        assert self.saved is not None
        return self.saved

    @override
    async def save(
        self,
        *,
        access: AccessContextDTO,
        facts: EmbeddingProfileCreationFactsDTO,
        operation_id: OperationId,
        profile: EmbeddingProfileDTO,
        initial_actions: tuple[EmbeddingProfileAction, ...],
        can_grant: Literal[True],
    ) -> None:
        assert (
            access == ACCESS
            and facts == self.facts
            and operation_id == NEW_RESERVATION.operation_id
        )
        self.events.append("save")
        self.saved = EmbeddingProfileCreationDTO(
            profile=profile,
            operation=SAVED_RESULT,
            project_access_revision=facts.access_revision + 1,
            initial_actions=initial_actions,
            can_grant=can_grant,
        )


type _Creation = tuple[
    list[str],
    MockEmbeddingProfileCreationRepository,
    MockOperationIdempotency,
    MockTransactions,
    EmbeddingProfileCreationService,
]


@pytest.fixture
def creation() -> _Creation:
    events: list[str] = []
    repository = MockEmbeddingProfileCreationRepository(events)
    idempotency = MockOperationIdempotency(events)
    transactions = MockTransactions(events)
    service = EmbeddingProfileCreationService(
        repository,
        idempotency,
        RequestFingerprintService(RequestFingerprintKey(b"B" * 32)),
        transactions=transactions,
        official_destinations=None,
    )
    idempotency.result = NEW_RESERVATION
    return events, repository, idempotency, transactions, service


@pytest.mark.asyncio
async def test_creates_once_and_replays_the_original_layout_and_assignments(
    creation: _Creation,
) -> None:
    events, repository, idempotency, _, service = creation
    result = await service.create(access=ACCESS, command=_COMMAND, context=_CONTEXT)

    assert events == ["begin", "authority", "reserve", "selection", "save", "complete", "commit"]
    assert result.operation.created and result.project_access_revision == 8
    assert result.profile.name == _COMMAND.name
    assert result.profile.display_name == _COMMAND.display_name
    assert result.profile.reviewed.selection == _COMMAND.selection
    assert result.profile.reviewed.effective == _COMMAND.effective
    assert result.profile.reviewed.adopted_suggestions == ()
    assert result.profile.layout.organization_id == ORGANIZATION_ID
    assert result.profile.layout.project_id == PROJECT_ID
    assert result.profile.layout.shard_count == 2
    assert result.profile.shard_names == (
        result.profile.layout.collection_name(0),
        result.profile.layout.collection_name(1),
    )
    assert (
        len(
            {
                result.profile.layout.embedding_profile_id.value,
                result.profile.layout.layout_id.value,
                result.profile.vector_index_id.value,
            }
        )
        == 3
    )
    assert tuple(action.value for action in result.initial_actions) == (
        "view-embedding-profile",
        "use-embedding-profile",
    )
    assert result.can_grant is True
    assert idempotency.lookup_authority is not None
    assert idempotency.lookup_authority.family is OperationLookupAuthorityFamily.PROJECT_ACTION_USE
    assert idempotency.lookup_authority.action_id.value == "create-embedding-profiles"
    idempotency.lookup_authority.require_supported_scope(
        project_id=PROJECT_ID,
        method=_CONTEXT.method.value,
        requested_route=_CONTEXT.requested_route,
    )
    fingerprint = idempotency.fingerprint

    events.clear()
    repository.live_connection = None
    repository.facts = replace(_FACTS, access_revision=12)
    idempotency.result = SAVED_RESULT
    replayed = await service.create(access=ACCESS, command=_COMMAND, context=_CONTEXT)

    assert replayed == replace(result, operation=SAVED_RESULT)
    assert idempotency.fingerprint == fingerprint
    assert events == ["begin", "authority", "reserve", "original", "commit"]


@pytest.mark.asyncio
@pytest.mark.parametrize("application_actor", [False, True])
async def test_checks_current_human_create_before_reservation_or_replay(
    creation: _Creation,
    application_actor: bool,
) -> None:
    events, repository, idempotency, _, service = creation
    idempotency.result = SAVED_RESULT
    access = ACCESS
    if application_actor:
        access = replace(
            ACCESS,
            authentication_evidence=ApplicationKeyAuthenticationDTO(ApplicationKeyId(UUID(int=6))),
        )
        action = replace(
            _FACTS.action,
            principal=replace(_FACTS.action.principal, kind=PrincipalKind.APPLICATION),
            oauth_credential_facts=None,
        )
    else:
        action = replace(_FACTS.action, has_exact_action_grant=False)
    repository.facts = replace(_FACTS, action=action)

    with pytest.raises(AccessDeniedError):
        await service.create(access=access, command=_COMMAND, context=_CONTEXT)

    assert events == ["begin", "authority", "rollback"]


@pytest.mark.asyncio
async def test_unavailable_connection_does_not_save_or_complete(
    creation: _Creation,
) -> None:
    events, repository, _, _, service = creation
    repository.live_connection = None

    with pytest.raises(ResourceNotFoundError):
        await service.create(access=ACCESS, command=_COMMAND, context=_CONTEXT)

    assert events == ["begin", "authority", "reserve", "selection", "rollback"]
    assert repository.saved is None


@pytest.mark.asyncio
async def test_public_creation_rechecks_destination_only_for_fresh_requests(
    creation: _Creation,
) -> None:
    events, repository, idempotency, transactions, _ = creation
    fingerprints = RequestFingerprintService(RequestFingerprintKey(b"B" * 32))
    allowed = EmbeddingProfileCreationService(
        repository,
        idempotency,
        fingerprints,
        transactions=transactions,
        official_destinations=ModelConnectionDestinationPolicy(
            https_base_urls=frozenset({"https://api.openai.com/v1"})
        ),
    )
    blocked = EmbeddingProfileCreationService(
        repository,
        idempotency,
        fingerprints,
        transactions=transactions,
        official_destinations=ModelConnectionDestinationPolicy(),
    )

    with pytest.raises(ConflictError):
        await blocked.create(access=ACCESS, command=_COMMAND, context=_CONTEXT)
    assert events == ["begin", "authority", "reserve", "selection", "rollback"]
    assert repository.saved is None

    events.clear()
    official = repository.live_connection
    assert official is not None
    repository.live_connection = replace(
        official, provider=ModelConnectionProvider.OPENAI_COMPATIBLE
    )
    with pytest.raises(ConflictError):
        await allowed.create(access=ACCESS, command=_COMMAND, context=_CONTEXT)
    assert events == ["begin", "authority", "reserve", "selection", "rollback"]
    assert repository.saved is None

    events.clear()
    repository.live_connection = official
    original = await allowed.create(access=ACCESS, command=_COMMAND, context=_CONTEXT)
    fingerprint = idempotency.fingerprint
    events.clear()
    idempotency.result = SAVED_RESULT
    repository.facts = replace(_FACTS, access_revision=8)
    replayed = await blocked.create(access=ACCESS, command=_COMMAND, context=_CONTEXT)
    assert replayed == replace(original, operation=SAVED_RESULT)
    assert idempotency.fingerprint == fingerprint
    assert events == ["begin", "authority", "reserve", "original", "commit"]


@pytest.mark.asyncio
async def test_changed_effective_settings_have_distinct_request_and_semantic_fingerprints(
    creation: _Creation,
) -> None:
    events, repository, idempotency, _, service = creation
    original = await service.create(access=ACCESS, command=_COMMAND, context=_CONTEXT)
    fingerprint = idempotency.fingerprint
    events.clear()
    changed = replace(
        _COMMAND,
        effective=replace(_COMMAND.effective, settings=replace(_SETTINGS, query_prefix="query:")),
    )
    idempotency.result = SAVED_RESULT
    repository.facts = replace(_FACTS, access_revision=8)
    with pytest.raises(ConflictError, match="original"):
        await service.create(access=ACCESS, command=changed, context=_CONTEXT)

    assert idempotency.fingerprint != fingerprint
    assert events == ["begin", "authority", "reserve", "original", "rollback"]

    events.clear()
    idempotency.result = NEW_RESERVATION
    retry_context = replace(_CONTEXT, key=IdempotencyKey("second-embedding-profile"))
    new_definition = replace(changed, name=ResourceName("support-embeddings-v2"))
    result = await service.create(access=ACCESS, command=new_definition, context=retry_context)

    assert result.profile.reviewed.fingerprint != original.profile.reviewed.fingerprint
    assert (
        result.profile.layout.embedding_profile_id != original.profile.layout.embedding_profile_id
    )


@pytest.mark.asyncio
async def test_replay_rejects_incoherent_saved_shards_without_readmitting_connection(
    creation: _Creation,
) -> None:
    events, repository, idempotency, _, service = creation
    await service.create(access=ACCESS, command=_COMMAND, context=_CONTEXT)
    assert repository.saved is not None
    corrupt_profile = replace(repository.saved.profile, shard_names=("exchanged", "shard-names"))
    repository.saved = replace(repository.saved, profile=corrupt_profile)
    events.clear()
    repository.facts = replace(_FACTS, access_revision=8)
    idempotency.result = SAVED_RESULT

    with pytest.raises(ConflictError, match="original"):
        await service.create(access=ACCESS, command=_COMMAND, context=_CONTEXT)

    assert events == ["begin", "authority", "reserve", "original", "rollback"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command",
    [
        replace(_COMMAND, selection=replace(_COMMAND.selection, role=ModelRole.GENERATION)),
        replace(_COMMAND, selection=replace(_COMMAND.selection, project_id=ProjectId(UUID(int=8)))),
        replace(
            _COMMAND,
            effective=replace(_COMMAND.effective, settings=replace(_SETTINGS, dimensions=1537)),
        ),
    ],
)
async def test_invalid_embedding_definition_never_reserves(
    creation: _Creation,
    command: CreateEmbeddingProfileCommand,
) -> None:
    _, _, idempotency, _, service = creation

    with pytest.raises(InvalidInputError):
        await service.create(access=ACCESS, command=command, context=_CONTEXT)

    assert idempotency.calls == 0


@pytest.mark.asyncio
async def test_exhausted_revision_prevents_any_new_effects(
    creation: _Creation,
) -> None:
    events, repository, _, _, service = creation
    repository.facts = replace(_FACTS, access_revision=RevisionValidation.MAX_VALUE)

    with pytest.raises(ConflictError, match="exhausted"):
        await service.create(access=ACCESS, command=_COMMAND, context=_CONTEXT)

    assert events == ["begin", "authority", "reserve", "rollback"]
    assert repository.saved is None


@pytest.mark.asyncio
async def test_commit_failure_leaves_no_returned_receipt(
    creation: _Creation,
) -> None:
    events, _, _, transactions, service = creation
    transactions.error = TimeoutError()

    with pytest.raises(DependencyUnavailableError):
        await service.create(access=ACCESS, command=_COMMAND, context=_CONTEXT)

    assert events == ["begin", "authority", "reserve", "selection", "save", "complete", "rollback"]
