"""Count only real current human responsibility, without providing grant/group workflows."""

import os
from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select, update
from tests.support.project_membership_postgres_scenarios import (
    change_membership,
    seed_membership_project,
)

from inframeld_backend.access.application.dtos.identity_recovery_event_dto import (
    IdentityRecoveryEventDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.identity_recovery_event_kind import (
    IdentityRecoveryEventKind,
)
from inframeld_backend.access.domain.enums.model_connection_authentication import (
    ModelConnectionAuthentication,
)
from inframeld_backend.access.domain.enums.model_connection_provider import ModelConnectionProvider
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.value_objects.identity_recovery_flow_id import (
    IdentityRecoveryFlowId,
)
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
)
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.model_connection_row import ModelConnectionRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.writers.postgres_identity_recovery_admission_writer import (
    PostgresIdentityRecoveryAdmissionWriter,
)
from inframeld_backend.indexing.application.commands.create_embedding_profile_command import (
    CreateEmbeddingProfileCommand,
)
from inframeld_backend.indexing.application.services.embedding_profile_creation_service import (
    EmbeddingProfileCreationService,
)
from inframeld_backend.indexing.domain.enums.embedding_profile_action import EmbeddingProfileAction
from inframeld_backend.indexing.infrastructure.repositories.postgres_embedding_profile_creation_repository import (
    PostgresEmbeddingProfileCreationRepository,
)
from inframeld_backend.indexing.infrastructure.rows.embedding_profile_action_grant_row import (
    EmbeddingProfileActionGrantRow,
)
from inframeld_backend.indexing.infrastructure.rows.embedding_profile_creation_result_row import (
    EmbeddingProfileCreationResultRow,
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
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires PostgreSQL integration services",
    ),
]


@pytest.mark.parametrize("candidate", ["eligible", "suspended", "recovery", "missing-identity"])
async def test_only_eligible_coherent_human_can_preserve_an_exact_action(
    database: Database, candidate: str
) -> None:
    seed = await seed_membership_project(database)
    await change_membership(database, seed, revision=1, key="join")
    carol = uuid4()
    identity = VerifiedHumanIdentityDTO(
        seed.actor.binding.identity.authority, IdentitySubject(str(UUID(int=201)))
    )
    project, organization = seed.project.project_id.value, seed.actor.organization_id.value
    async with database.session() as session, session.begin():
        session.add(
            PrincipalRow(
                id=carol,
                organization_id=organization,
                kind=PrincipalKind.HUMAN,
                status=PrincipalStatus.SUSPENDED
                if candidate == "suspended"
                else PrincipalStatus.ACTIVE,
                display_name="Carol",
            )
        )
        await session.flush()
        if candidate != "missing-identity":
            session.add(
                HumanIdentityLinkRow(
                    authority=identity.authority.value,
                    subject=identity.subject.value,
                    organization_id=organization,
                    principal_id=carol,
                    principal_kind=PrincipalKind.HUMAN,
                )
            )
            session.add(
                HumanCredentialVersionRow(
                    installation_id=seed.actor.binding.installation_id.value,
                    authority=identity.authority.value,
                    subject=identity.subject.value,
                    version=1,
                )
            )
        session.add(
            ProjectMembershipRow(
                project_id=project,
                organization_id=organization,
                principal_id=carol,
                principal_kind=PrincipalKind.HUMAN,
            )
        )
        await session.flush()
        for principal in (carol, seed.bob_id.value):
            session.add(
                ProjectActionGrantRow(
                    project_id=project,
                    recipient_principal_id=principal,
                    recipient_kind=PrincipalKind.HUMAN,
                    action="create-access-groups",
                    can_grant=True,
                )
            )
        await session.execute(
            delete(ProjectActionGrantRow).where(
                ProjectActionGrantRow.project_id == project,
                ProjectActionGrantRow.recipient_principal_id
                == seed.actor.access.actor_principal_id.value,
                ProjectActionGrantRow.action == "create-access-groups",
            )
        )
    if candidate == "recovery":
        async with database.session() as session, session.begin():
            await PostgresIdentityRecoveryAdmissionWriter(
                session,
                installation_id=seed.actor.binding.installation_id,
                authority=identity.authority,
            ).reserve(
                IdentityRecoveryEventDTO(
                    IdentityRecoveryFlowId(uuid4()), identity, IdentityRecoveryEventKind.RECOVERY
                )
            )
    if candidate == "eligible":
        assert (
            await change_membership(database, seed, revision=2, key="leave", remove=True)
        ).changed
    else:
        with pytest.raises(ConflictError):
            await change_membership(database, seed, revision=2, key="leave", remove=True)
        async with database.session() as session:
            assert await session.get(ProjectMembershipRow, (project, seed.bob_id.value)) is not None
            assert await session.scalar(select(ProjectRow.access_revision)) == 2


async def test_recovery_blocked_recipient_can_leave_but_cannot_rejoin(database: Database) -> None:
    seed = await seed_membership_project(database)
    await change_membership(database, seed, revision=1, key="join")
    identity = VerifiedHumanIdentityDTO(
        seed.actor.binding.identity.authority, IdentitySubject(str(UUID(int=200)))
    )
    async with database.session() as session, session.begin():
        await PostgresIdentityRecoveryAdmissionWriter(
            session,
            installation_id=seed.actor.binding.installation_id,
            authority=identity.authority,
        ).reserve(
            IdentityRecoveryEventDTO(
                IdentityRecoveryFlowId(uuid4()), identity, IdentityRecoveryEventKind.RECOVERY
            )
        )
    removed = await change_membership(database, seed, revision=2, key="leave", remove=True)
    assert removed.changed and removed.access_revision == 3
    with pytest.raises(ConflictError):
        await change_membership(database, seed, revision=3, key="blocked-rejoin")


async def test_self_departure_keeps_grants_assigned_to_remaining_human_and_blocks_later_replay(
    database: Database,
) -> None:
    seed = await seed_membership_project(database)
    await change_membership(database, seed, revision=1, key="join")
    project = seed.project.project_id.value
    async with database.session() as session, session.begin():
        actions = (
            await session.scalars(
                select(ProjectActionGrantRow.action).where(
                    ProjectActionGrantRow.project_id == project
                )
            )
        ).all()
        for action in actions:
            session.add(
                ProjectActionGrantRow(
                    project_id=project,
                    recipient_principal_id=seed.bob_id.value,
                    recipient_kind=PrincipalKind.HUMAN,
                    action=action,
                    can_grant=True,
                    assigned_by_principal_id=seed.actor.access.actor_principal_id.value,
                )
            )
    left = await change_membership(
        database,
        seed,
        principal_id=seed.actor.access.actor_principal_id,
        revision=2,
        key="self-departure",
        remove=True,
    )
    assert left.changed
    with pytest.raises(ResourceNotFoundError):
        await change_membership(
            database,
            seed,
            principal_id=seed.actor.access.actor_principal_id,
            revision=2,
            key="self-departure",
            remove=True,
        )
    bob = seed.bob_access
    with pytest.raises(ConflictError):
        await change_membership(
            database, seed, revision=3, key="last-human", remove=True, access=bob
        )


async def test_embedding_creator_can_leave_only_after_exact_grantor_handover(
    database: Database,
) -> None:
    seed = await seed_membership_project(database)
    await change_membership(database, seed, revision=1, key="join")
    project = seed.project.project_id
    alice, bob = seed.actor.access.actor_principal_id.value, seed.bob_id.value
    connection_id = ModelConnectionId(uuid4())
    async with database.session() as session, session.begin():
        session.add(
            ModelConnectionRow(
                id=connection_id.value,
                project_id=project.value,
                organization_id=seed.actor.organization_id.value,
                name="profile-fixture",
                display_name="Profile fixture",
                provider=ModelConnectionProvider.OPENAI.value,
                base_url="https://api.openai.com/v1",
                api_version=None,
                authentication=ModelConnectionAuthentication.API_KEY.value,
            )
        )
        session.add(
            ProjectActionGrantRow(
                project_id=project.value,
                recipient_principal_id=bob,
                recipient_kind=PrincipalKind.HUMAN,
                action=ProjectAction.CREATE_EMBEDDING_PROFILES.value,
                can_grant=False,
                assigned_by_principal_id=alice,
            )
        )

    command = CreateEmbeddingProfileCommand(
        project_id=project,
        name=ResourceName("bob-profile"),
        display_name=SubmittedDisplayName("Bob's profile"),
        selection=ModelSelectionDTO(project, connection_id, "fixture-model", ModelRole.EMBEDDING),
        effective=EffectiveModelSettingsDTO(
            1024,
            ModelTokenBoundDTO(ModelTokenBoundKind.EXACT, "fixture-tokenizer", "fixture-revision"),
            EmbeddingModelSettingsDTO(
                dimensions=8,
                normalization=EmbeddingNormalization.NONE,
                distance=EmbeddingDistance.COSINE,
                document_prefix="",
                query_prefix="",
                expected_provider="openai",
                role=ModelRole.EMBEDDING,
            ),
        ),
    )
    context = IdempotencyContextDTO(
        HttpMethod.POST,
        f"/v1/projects/{project.value}/embedding-profiles",
        IdempotencyKey("bob-profile"),
    )
    async with database.session() as session:
        service = EmbeddingProfileCreationService(
            PostgresEmbeddingProfileCreationRepository(session),
            IdempotencyService(PostgresOperationReservationWriter(session)),
            RequestFingerprintService(RequestFingerprintKey(b"E" * 32)),
            transactions=SqlAlchemyTransactionManager(session),
            official_destinations=None,
        )
        created = await service.create(access=seed.bob_access, command=command, context=context)
        other = await service.create(
            access=seed.actor.access,
            command=replace(command, name=ResourceName("alice-profile")),
            context=replace(context, key=IdempotencyKey("alice-profile")),
        )
    profile = created.profile.layout.embedding_profile_id.value
    other_profile = other.profile.layout.embedding_profile_id.value
    revision = other.project_access_revision
    grant = EmbeddingProfileActionGrantRow
    async with database.session() as session, session.begin():
        session.add(
            grant(
                project_id=project.value,
                embedding_profile_id=other_profile,
                recipient_principal_id=bob,
                recipient_kind=PrincipalKind.HUMAN,
                action=EmbeddingProfileAction.USE.value,
                can_grant=False,
                assigned_by_principal_id=alice,
            )
        )

    # Alice already grants both actions on her own profile. Those grants cannot preserve Bob's.
    for action in (None, EmbeddingProfileAction.USE, EmbeddingProfileAction.VIEW):
        if action is not None:
            async with database.session() as session, session.begin():
                session.add(
                    grant(
                        project_id=project.value,
                        embedding_profile_id=profile,
                        recipient_principal_id=alice,
                        recipient_kind=PrincipalKind.HUMAN,
                        action=action.value,
                        can_grant=action is EmbeddingProfileAction.USE,
                        assigned_by_principal_id=bob,
                    )
                )
        with pytest.raises(ConflictError, match="responsibility without an eligible human"):
            await change_membership(
                database, seed, revision=revision, key="leave-embedding-creator", remove=True
            )
        async with database.session() as session:
            assert await session.get(ProjectMembershipRow, (project.value, bob)) is not None
            assert await session.scalar(select(ProjectRow.access_revision)) == revision
            affected = await session.scalars(
                select(grant).where(
                    grant.project_id == project.value, grant.recipient_principal_id == bob
                )
            )
            assert {(row.embedding_profile_id, row.action, row.can_grant) for row in affected} == {
                (profile, EmbeddingProfileAction.VIEW.value, True),
                (profile, EmbeddingProfileAction.USE.value, True),
                (other_profile, EmbeddingProfileAction.USE.value, False),
            }

    async with database.session() as session, session.begin():
        await session.execute(
            update(grant)
            .where(
                grant.project_id == project.value,
                grant.embedding_profile_id == profile,
                grant.recipient_principal_id == alice,
                grant.action == EmbeddingProfileAction.VIEW.value,
            )
            .values(can_grant=True)
        )
    removed = await change_membership(
        database, seed, revision=revision, key="leave-embedding-creator", remove=True
    )

    assert removed.changed and removed.access_revision == revision + 1
    async with database.session() as session:
        assert await session.get(ProjectMembershipRow, (project.value, bob)) is None
        grants = await session.scalars(select(grant).where(grant.project_id == project.value))
        assert {
            (row.embedding_profile_id, row.recipient_principal_id, row.action, row.can_grant)
            for row in grants
        } == {
            (profile_id, alice, action.value, True)
            for profile_id in (profile, other_profile)
            for action in EmbeddingProfileAction
        }
        original = await session.get(
            EmbeddingProfileCreationResultRow, created.operation.operation_id.value
        )
        assert original is not None
        assert (original.embedding_profile_id, original.creator_principal_id) == (profile, bob)
        assert original.initial_actions == [action.value for action in EmbeddingProfileAction]
        assert original.project_access_revision == created.project_access_revision
