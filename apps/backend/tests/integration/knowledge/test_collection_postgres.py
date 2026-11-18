"""Exercise private Collection creation and selection under current authority."""

import os
from datetime import UTC, datetime
from functools import partial
from hashlib import sha256
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from tests.support.project_creation_scenarios import (
    ProjectCreationSeedDTO,
    create_project,
    seed_project_creator,
)

from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.value_objects.document_version_id import DocumentVersionId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.access_group_row import AccessGroupRow
from inframeld_backend.access.infrastructure.rows.group_membership_row import GroupMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.knowledge.application.dtos.collection_revision_dto import (
    CollectionRevisionDTO,
)
from inframeld_backend.knowledge.application.value_objects.collection_id import CollectionId
from inframeld_backend.knowledge.application.value_objects.collection_revision_id import (
    CollectionRevisionId,
)
from inframeld_backend.knowledge.infrastructure.repositories.postgres_collection_repository import (
    PostgresCollectionRepository,
)
from inframeld_backend.knowledge.infrastructure.rows.collection_action_grant_row import (
    CollectionActionGrantRow,
)
from inframeld_backend.knowledge.infrastructure.rows.collection_revision_row import (
    CollectionRevisionRow,
)
from inframeld_backend.knowledge.infrastructure.rows.collection_row import CollectionRow
from inframeld_backend.knowledge.infrastructure.rows.document_group_row import DocumentGroupRow
from inframeld_backend.knowledge.infrastructure.rows.document_row import DocumentRow
from inframeld_backend.knowledge.infrastructure.rows.document_version_row import DocumentVersionRow
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.artifact_attempt_row import ArtifactAttemptRow

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires isolated PostgreSQL integration services",
    ),
]


async def test_creator_grants_empty_revision_and_original_replay_are_atomic(
    database: Database,
) -> None:
    creator = await seed_project_creator(database)
    project = (await create_project(database, creator)).project.project_id
    operation = OperationId(str(uuid4()))
    name = ResourceName("support-library")
    display_name = SubmittedDisplayName("Support Library")
    async with database.session() as session, session.begin():
        project_row = await session.get(ProjectRow, project.value)
        assert project_row is not None
        initial_project_revision = project_row.access_revision
        result = await PostgresCollectionRepository(session).create(
            access=creator.access,
            project_id=project,
            name=name,
            display_name=display_name,
            operation_id=operation,
        )

    async with database.session() as session, session.begin():
        collection = await session.get(CollectionRow, result.collection_id.value)
        revision = await session.get(CollectionRevisionRow, result.revision_id.value)
        assert collection is not None and revision is not None
        assert (collection.name, collection.display_name) == (name.value, display_name.value)
        assert collection.current_revision_id == revision.id and revision.base_revision_id is None
        assert result.version_ids == ()
        grants = (
            await session.scalars(
                select(CollectionActionGrantRow).where(
                    CollectionActionGrantRow.collection_id == collection.id
                )
            )
        ).all()
        assert {grant.action for grant in grants} == {
            "view-collection",
            "edit-collection",
            "delete-collection",
        }
        assert all(
            grant.can_grant
            and grant.recipient_principal_id == creator.access.actor_principal_id.value
            for grant in grants
        )
        audit = await session.scalar(
            select(AccessAuditEventRow).where(AccessAuditEventRow.correlation_id == operation.value)
        )
        assert audit is not None and audit.target_id == collection.id
        # Replaying the original creation cannot put back a removed grant.
        await session.delete(next(grant for grant in grants if grant.action == "edit-collection"))

    async with database.session() as session, session.begin():
        original = await PostgresCollectionRepository(session).create(
            access=creator.access,
            project_id=project,
            name=name,
            display_name=display_name,
            operation_id=operation,
        )
        assert original == result
        remaining = (
            await session.scalars(
                select(CollectionActionGrantRow.action).where(
                    CollectionActionGrantRow.collection_id == result.collection_id.value
                )
            )
        ).all()
        assert set(remaining) == {"view-collection", "delete-collection"}
        project_row = await session.get(ProjectRow, project.value)
        assert project_row is not None
        assert project_row.access_revision == initial_project_revision + 1
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(AccessAuditEventRow.correlation_id == operation.value)
            )
            == 1
        )
        with pytest.raises(ConflictError):
            await PostgresCollectionRepository(session).create(
                access=creator.access,
                project_id=project,
                name=name,
                display_name=SubmittedDisplayName("Changed Display Name"),
                operation_id=operation,
            )
        project_row.access_revision = RevisionValidation.MAX_VALUE
        await session.flush()
        repo = PostgresCollectionRepository(session)
        with pytest.raises(ConflictError, match="The Project access revision is exhausted."):
            await repo.create(
                access=creator.access,
                project_id=project,
                name=ResourceName("different-library"),
                display_name=SubmittedDisplayName("Different Library"),
                operation_id=OperationId(str(uuid4())),
            )
        assert (
            await repo.create(
                access=creator.access,
                project_id=project,
                name=name,
                display_name=display_name,
                operation_id=operation,
            )
            == result
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CollectionRow)
                .where(CollectionRow.project_id == project.value)
            )
            == 1
        )


async def test_selection_preserves_original_and_rechecks_edit_and_document_authority(
    database: Database,
) -> None:
    creator = await seed_project_creator(database)
    project = (await create_project(database, creator)).project.project_id
    original, alternate, group_id = await _seed_selected_versions(database, creator, project)
    initial = await _seed_editable_collection(database, creator, project)
    select_from_collection = partial(
        PostgresCollectionRepository.select,
        access=creator.access,
        project_id=project,
        collection_id=initial.collection_id,
    )
    operation = OperationId(str(uuid4()))
    async with database.session() as session, session.begin():
        repo = PostgresCollectionRepository(session)
        with pytest.raises(ConflictError):
            await select_from_collection(
                repo,
                expected_base=initial.revision_id,
                version_ids=(original, alternate),
                operation_id=operation,
            )
        first = await select_from_collection(
            repo,
            expected_base=initial.revision_id,
            version_ids=(original,),
            operation_id=operation,
        )
        second = await select_from_collection(
            repo,
            expected_base=first.revision_id,
            version_ids=(alternate,),
            operation_id=OperationId(str(uuid4())),
        )
        assert first.version_ids == (original,) and second.version_ids == (alternate,)

    async with database.session() as session, session.begin():
        repo = PostgresCollectionRepository(session)
        assert (
            await select_from_collection(
                repo,
                expected_base=initial.revision_id,
                version_ids=(original,),
                operation_id=operation,
            )
            == first
        )
        with pytest.raises(StaleRevisionError):
            await select_from_collection(
                repo,
                expected_base=initial.revision_id,
                version_ids=(),
                operation_id=OperationId(str(uuid4())),
            )
        with pytest.raises(AccessDeniedError):
            await select_from_collection(
                repo,
                expected_base=second.revision_id,
                version_ids=(DocumentVersionId(uuid4()),),
                operation_id=OperationId(str(uuid4())),
            )
        with pytest.raises(ConflictError):
            await select_from_collection(
                repo,
                expected_base=initial.revision_id,
                version_ids=(alternate,),
                operation_id=operation,
            )
        row = await session.get(CollectionRow, initial.collection_id.value)
        assert row is not None and row.current_revision_id == second.revision_id.value
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(AccessAuditEventRow.correlation_id == operation.value)
            )
            == 1
        )
        version = await session.get(DocumentVersionRow, original.value)
        assert version is not None
        attempt = await session.get(ArtifactAttemptRow, version.attempt_id)
        assert attempt is not None
        attempt.state = "retired"
        attempt.published = False
        attempt.retired = True
        await session.flush()
        with pytest.raises(AccessDeniedError):
            await select_from_collection(
                repo,
                expected_base=initial.revision_id,
                version_ids=(original,),
                operation_id=operation,
            )
        attempt.state = "published"
        attempt.published = True
        attempt.retired = False
        group_member = await session.get(
            GroupMembershipRow, (project.value, group_id, creator.access.actor_principal_id.value)
        )
        assert group_member is not None
        await session.delete(group_member)
        await session.flush()
        with pytest.raises(AccessDeniedError):
            await select_from_collection(
                repo,
                expected_base=initial.revision_id,
                version_ids=(original,),
                operation_id=operation,
            )

    async with database.session() as session, session.begin():
        session.add(
            GroupMembershipRow(
                project_id=project.value,
                group_id=group_id,
                principal_id=creator.access.actor_principal_id.value,
            )
        )
        version = await session.get(DocumentVersionRow, original.value)
        assert version is not None
        document = await session.get(DocumentRow, version.document_id)
        assert document is not None
        document.erasure_operation_id = str(uuid4())
        document.erasure_blocked_at = datetime.now(UTC)

    async with database.session() as session, session.begin():
        with pytest.raises(AccessDeniedError):
            await select_from_collection(
                PostgresCollectionRepository(session),
                expected_base=initial.revision_id,
                version_ids=(original,),
                operation_id=operation,
            )
        edit = await session.get(
            CollectionActionGrantRow,
            (
                project.value,
                initial.collection_id.value,
                creator.access.actor_principal_id.value,
                "edit-collection",
            ),
        )
        assert edit is not None
        await session.delete(edit)

    async with database.session() as session, session.begin():
        with pytest.raises(AccessDeniedError):
            await select_from_collection(
                PostgresCollectionRepository(session),
                expected_base=second.revision_id,
                version_ids=(),
                operation_id=OperationId(str(uuid4())),
            )


async def _seed_editable_collection(
    database: Database, creator: ProjectCreationSeedDTO, project: ProjectId
) -> CollectionRevisionDTO:
    collection = CollectionId(uuid4())
    revision = CollectionRevisionId(uuid4())
    scope = {
        "installation_id": creator.binding.installation_id.value,
        "organization_id": creator.organization_id.value,
        "project_id": project.value,
    }
    actor = creator.access.actor_principal_id.value
    async with database.session() as session, session.begin():
        session.add(
            CollectionRow(
                id=collection.value,
                **scope,
                name="selected-library",
                display_name="Selected Library",
                current_revision_id=revision.value,
            )
        )
        await session.flush()
        session.add(
            CollectionRevisionRow(
                id=revision.value,
                collection_id=collection.value,
                **scope,
                operation_id=str(uuid4()),
                actor_principal_id=actor,
            )
        )
        session.add(
            CollectionActionGrantRow(
                project_id=project.value,
                collection_id=collection.value,
                recipient_principal_id=actor,
                action="edit-collection",
                recipient_kind=PrincipalKind.HUMAN,
                can_grant=True,
                assigned_by_principal_id=actor,
            )
        )
    return CollectionRevisionDTO(collection_id=collection, revision_id=revision, version_ids=())


async def _seed_selected_versions(
    database: Database, creator: ProjectCreationSeedDTO, project: ProjectId
) -> tuple[DocumentVersionId, DocumentVersionId, UUID]:
    scope = {
        "installation_id": creator.binding.installation_id.value,
        "organization_id": creator.organization_id.value,
        "project_id": project.value,
    }
    group_id = uuid4()
    document_id = uuid4()
    original = DocumentVersionId(uuid4())
    alternate = DocumentVersionId(uuid4())
    async with database.session() as session, session.begin():
        session.add(AccessGroupRow(id=group_id, project_id=project.value, name="Readers"))
        session.add(DocumentRow(id=document_id, **scope))
        await session.flush()
        session.add(
            GroupMembershipRow(
                project_id=project.value,
                group_id=group_id,
                principal_id=creator.access.actor_principal_id.value,
            )
        )
        session.add(
            DocumentGroupRow(document_id=document_id, group_id=group_id, project_id=project.value)
        )
        for version, body in ((original, b"first"), (alternate, b"second")):
            attempt_id = uuid4()
            digest = sha256(body).digest()
            session.add(
                ArtifactAttemptRow(
                    id=attempt_id,
                    artifact_id=uuid4(),
                    installation_id=creator.binding.installation_id.value,
                    organization_id=creator.organization_id.value,
                    project_id=project.value,
                    state="published",
                    length=len(body),
                    digest=digest,
                    published=True,
                    put_pending=True,
                    put_confirmed=True,
                )
            )
            await session.flush()
            session.add(
                DocumentVersionRow(
                    id=version.value,
                    **scope,
                    document_id=document_id,
                    attempt_id=attempt_id,
                    filename="selected.pdf",
                    media_type="application/pdf",
                    length=len(body),
                    digest=digest,
                )
            )
    return original, alternate, group_id
