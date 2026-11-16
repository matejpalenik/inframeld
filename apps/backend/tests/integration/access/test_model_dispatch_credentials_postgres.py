import os
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import update
from tests.support.project_creation_scenarios import ProjectCreationSeedDTO, create_project
from tests.support.spending_scenarios import (
    finish_fixture_job,
    seed_human_work,
    seed_spending_scenario,
)

from inframeld_backend.access.application.commands.change_model_connection_credential_command import (
    ChangeModelConnectionCredentialCommand,
)
from inframeld_backend.access.application.commands.change_model_connection_grant_command import (
    ChangeModelConnectionGrantCommand,
)
from inframeld_backend.access.application.commands.create_model_connection_command import (
    CreateModelConnectionCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.model_connection_access_dto import (
    ModelConnectionAccessDTO,
)
from inframeld_backend.access.application.dtos.model_connection_creation_dto import (
    ModelConnectionCreationDTO,
)
from inframeld_backend.access.application.dtos.model_dispatch_credential_dto import (
    ModelDispatchCredentialDTO,
)
from inframeld_backend.access.application.services.admitted_work_authorization_service import (
    AdmittedWorkAuthorizationService,
)
from inframeld_backend.access.application.services.model_dispatch_credential_service import (
    ModelDispatchCredentialService,
)
from inframeld_backend.access.application.value_objects.provider_credential_value import (
    ProviderCredentialValue,
)
from inframeld_backend.access.domain.enums.model_connection_action import ModelConnectionAction
from inframeld_backend.access.domain.enums.model_connection_authentication import (
    ModelConnectionAuthentication,
)
from inframeld_backend.access.domain.enums.model_connection_provider import ModelConnectionProvider
from inframeld_backend.access.domain.policies.model_connection_destination_policy import (
    ModelConnectionDestinationPolicy,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.readers.postgres_admitted_work_facts_reader import (
    PostgresAdmittedWorkFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_model_dispatch_credential_reader import (
    PostgresModelDispatchCredentialReader,
)
from inframeld_backend.access.infrastructure.rows.model_connection_row import ModelConnectionRow
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.settings.model_connection_destination_settings import (
    ModelConnectionDestinationSettings,
)
from inframeld_backend.access.infrastructure.settings.provider_credential_settings import (
    ProviderCredentialSettings,
)
from inframeld_backend.bootstrap.model_connection_composition import (
    open_model_connection_creation,
    open_model_connection_credentials,
    open_model_connection_grant_change,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.dtos.product_job_binding_dto import ProductJobBindingDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.errors.job_errors import (
    JobFenceLostError,
    JobStoppedError,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.job_fence import JobFence
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)
from inframeld_backend.shared.infrastructure.repositories.postgres_job_store import PostgresJobStore
from inframeld_backend.shared.infrastructure.resources.database import Database

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1", reason="Requires isolated PostgreSQL"
    ),
]

_URL = "https://models.example.test/v1"
_DESTINATIONS = ModelConnectionDestinationSettings(https_base_urls=frozenset({_URL}))
_POLICY = ModelConnectionDestinationPolicy(https_base_urls=_DESTINATIONS.https_base_urls)
_FINGERPRINT_KEY = RequestFingerprintKey(b"F" * 32)
_FINGERPRINTS = RequestFingerprintService(_FINGERPRINT_KEY)


@pytest.fixture
def provider_settings(tmp_path: Path) -> ProviderCredentialSettings:
    key = bytes(range(32))
    path = tmp_path / "provider.key"
    path.write_bytes(key)
    path.chmod(0o600)
    return ProviderCredentialSettings(key_file=path, expected_key_id=sha256(key).hexdigest())


async def _create_connection(
    database: Database, access: AccessContextDTO, project: ProjectId, name: str
) -> ModelConnectionCreationDTO:
    async with open_model_connection_creation(database, _FINGERPRINTS, _DESTINATIONS) as creator:
        return await creator.create(
            access=access,
            command=CreateModelConnectionCommand(
                project,
                ResourceName(name),
                SubmittedDisplayName("Provider fixture"),
                ModelConnectionAccessDTO(
                    ModelConnectionProvider.OPENAI_COMPATIBLE,
                    _URL,
                    None,
                    ModelConnectionAuthentication.API_KEY,
                ),
            ),
            context=IdempotencyContextDTO(
                HttpMethod.POST,
                f"/v1/projects/{project.value}/model-connections",
                IdempotencyKey(name),
            ),
        )


async def _change_credential(
    database: Database,
    access: AccessContextDTO,
    connection: ModelConnectionCreationDTO,
    settings: ProviderCredentialSettings,
    revision: int,
    value: str | None,
) -> None:
    project, selected = connection.connection.project_id, connection.connection.connection_id
    async with open_model_connection_credentials(
        database, _FINGERPRINT_KEY, _DESTINATIONS, settings
    ) as credentials:
        await credentials.change(
            access,
            ChangeModelConnectionCredentialCommand(
                project,
                selected,
                revision,
                None if value is None else ProviderCredentialValue(value),
            ),
            IdempotencyContextDTO(
                HttpMethod.DELETE if value is None else HttpMethod.PUT,
                f"/v1/projects/{project.value}/model-connections/{selected.value}/credential",
                IdempotencyKey(f"credential-{revision}"),
            ),
        )


async def _snapshot(
    database: Database,
    attempt: JobAttemptContextDTO,
    selected: ModelConnectionId,
    revision: int,
    policy: ModelConnectionDestinationPolicy = _POLICY,
) -> ModelDispatchCredentialDTO:
    async with database.session() as session, session.begin():
        return await ModelDispatchCredentialService(
            AdmittedWorkAuthorizationService(PostgresAdmittedWorkFactsReader(session)),
            PostgresJobStore(session),
            PostgresModelDispatchCredentialReader(session),
            policy,
        ).read(attempt=attempt, connection_id=selected, admitted_access_revision=revision)


async def test_current_credential_tracks_rotation_removal_and_connection_revision(
    database: Database, provider_settings: ProviderCredentialSettings
) -> None:
    owner = await seed_spending_scenario(database, create_account=False)
    created = await _create_connection(database, owner.access, owner.project_id, "rotation")
    selected = created.connection.connection_id
    revision = created.connection.connection_access_revision

    with pytest.raises(ConflictError, match="current provider credential is required"):
        await _snapshot(database, owner.attempt, selected, revision)

    await _change_credential(database, owner.access, created, provider_settings, 0, "first-fixture")
    original = await _snapshot(database, owner.attempt, selected, revision)
    assert original.binding.revision == 1
    assert original.binding.project_id == owner.project_id
    assert original.binding.organization_id == owner.organization_id
    assert original.binding.connection_id == selected

    await _change_credential(
        database, owner.access, created, provider_settings, 1, "rotated-fixture"
    )
    rotated = await _snapshot(database, owner.attempt, selected, revision)
    assert rotated.binding == replace(original.binding, revision=2)
    assert rotated.envelope != original.envelope
    assert rotated.access_revision == original.access_revision == revision
    with pytest.raises(AccessDeniedError, match="destination is no longer approved"):
        await _snapshot(
            database, owner.attempt, selected, revision, ModelConnectionDestinationPolicy()
        )

    # Set up an independently changed stored selection because no connection-edit entry point exists.
    async with database.session() as session, session.begin():
        await session.execute(
            update(ModelConnectionRow)
            .where(ModelConnectionRow.id == selected.value)
            .values(access_revision=revision + 1)
        )
    with pytest.raises(StaleRevisionError):
        await _snapshot(database, owner.attempt, selected, revision)
    assert (
        await _snapshot(database, owner.attempt, selected, revision + 1)
    ).binding == rotated.binding

    await _change_credential(database, owner.access, created, provider_settings, 2, None)
    with pytest.raises(ConflictError, match="current provider credential is required"):
        await _snapshot(database, owner.attempt, selected, revision + 1)


async def test_current_credential_requires_exact_use_in_the_original_job_scope(
    database: Database, provider_settings: ProviderCredentialSettings
) -> None:
    owner = await seed_spending_scenario(database, create_account=False)
    created = await _create_connection(database, owner.access, owner.project_id, "exact-use")
    selected = created.connection.connection_id
    revision = created.connection.connection_access_revision
    await _change_credential(database, owner.access, created, provider_settings, 0, "use-fixture")
    binding = owner.attempt.binding
    assert isinstance(binding, ProductJobBindingDTO) and binding.authority.human_binding is not None
    async with database.session() as session:
        organization = await session.get(OrganizationRow, owner.organization_id.value)
        assert organization is not None
        other_creator = ProjectCreationSeedDTO(
            owner.access,
            owner.organization_id,
            organization.access_revision,
            binding.authority.human_binding,
        )
    other_project = await create_project(database, other_creator, name="other-project", key="other")
    other = await _create_connection(
        database, other_creator.access, other_project.project.project_id, "other-project"
    )
    await _change_credential(
        database, other_creator.access, other, provider_settings, 0, "unrelated-fixture"
    )
    # The same owner holds Use in both Projects, but the admitted work belongs to only one.
    with pytest.raises(AccessDeniedError):
        await _snapshot(
            database,
            owner.attempt,
            other.connection.connection_id,
            other.connection.connection_access_revision,
        )
    await finish_fixture_job(database, owner)
    applicant = await seed_human_work(database, owner, "reader-job")

    project_revision = created.project_access_revision

    async def set_grant(action: ModelConnectionAction, *, present: bool) -> None:
        nonlocal project_revision
        method = HttpMethod.PUT if present else HttpMethod.DELETE
        recipient = applicant.access.actor_principal_id
        async with open_model_connection_grant_change(database, _FINGERPRINTS) as changer:
            result = await changer.change(
                owner.access,
                ChangeModelConnectionGrantCommand(
                    selected, recipient, action, project_revision, False if present else None
                ),
                IdempotencyContextDTO(
                    method,
                    f"/v1/model-connections/{selected.value}/grants/{recipient.value}/{action.value}",
                    IdempotencyKey(f"{method.value}-{action.value}"),
                ),
            )
        project_revision = result.access_revision

    view, manage, use = (
        ModelConnectionAction.VIEW_CONFIGURATION,
        ModelConnectionAction.MANAGE,
        ModelConnectionAction.USE,
    )
    await set_grant(view, present=True)
    await set_grant(manage, present=True)
    with pytest.raises(AccessDeniedError):
        await _snapshot(database, applicant.attempt, selected, revision)

    await set_grant(view, present=False)
    await set_grant(manage, present=False)
    await set_grant(use, present=True)
    result = await _snapshot(database, applicant.attempt, selected, revision)
    assert result.binding.connection_id == selected and result.binding.revision == 1

    with pytest.raises(JobFenceLostError):
        await _snapshot(
            database, replace(applicant.attempt, fence=JobFence(uuid4())), selected, revision
        )
    await set_grant(use, present=False)
    with pytest.raises(AccessDeniedError):
        await _snapshot(database, applicant.attempt, selected, revision)

    async with database.session() as session, session.begin():
        await PostgresJobStore(session).request_cancel(applicant.attempt.job_id)
    with pytest.raises(JobStoppedError):
        await _snapshot(database, applicant.attempt, selected, revision)
