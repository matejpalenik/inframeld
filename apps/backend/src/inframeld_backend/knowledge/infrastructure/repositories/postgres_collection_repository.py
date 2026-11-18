import asyncio
from dataclasses import replace
from uuid import UUID, uuid4

from sqlalchemy import and_, exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_key_authentication_dto import (
    ApplicationKeyAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.application_key_verification_profile_dto import (
    ApplicationKeyVerificationProfileDTO,
)
from inframeld_backend.access.application.dtos.current_document_access_dto import (
    CurrentDocumentAccessDTO,
)
from inframeld_backend.access.application.dtos.project_action_target_dto import (
    ProjectActionTargetDTO,
)
from inframeld_backend.access.application.dtos.selected_document_source_dto import (
    SelectedDocumentSourceDTO,
)
from inframeld_backend.access.application.services.action_authorization_service import (
    ActionAuthorizationService,
)
from inframeld_backend.access.application.services.document_access_service import (
    DocumentAccessService,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.document_id import DocumentId
from inframeld_backend.access.domain.value_objects.document_source_id import DocumentSourceId
from inframeld_backend.access.domain.value_objects.document_version_id import DocumentVersionId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.readers.postgres_document_access_facts_reader import (
    PostgresDocumentAccessFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_action_facts_reader import (
    PostgresProjectActionFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_scope_lock import (
    PostgresProjectScopeLock,
)
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.knowledge.application.dtos.collection_revision_dto import (
    CollectionRevisionDTO,
)
from inframeld_backend.knowledge.application.value_objects.collection_id import CollectionId
from inframeld_backend.knowledge.application.value_objects.collection_revision_id import (
    CollectionRevisionId,
)
from inframeld_backend.knowledge.infrastructure.rows.collection_action_grant_row import (
    CollectionActionGrantRow,
)
from inframeld_backend.knowledge.infrastructure.rows.collection_revision_document_row import (
    CollectionRevisionDocumentRow,
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
    DependencyUnavailableError,
    InvalidInputError,
    ResourceNotFoundError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)
from inframeld_backend.shared.infrastructure.rows.artifact_attempt_row import ArtifactAttemptRow
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)

_EDIT = "edit-collection"
_CREATOR_ACTIONS = ("view-collection", _EDIT, "delete-collection")
_MAX_DOCUMENTS = 200


class PostgresCollectionRepository:
    """Write a Collection and its revisions in the caller's active transaction.

    The caller supplies the admitted original operation identity and owns commit
    and rollback. All changes precede any downstream work.
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        application_key_profile: ApplicationKeyVerificationProfileDTO | None = None,
    ) -> None:
        self._session = session
        self._action_facts = PostgresProjectActionFactsReader(
            session, application_key_profile=application_key_profile
        )
        self._document_access = DocumentAccessService(
            PostgresDocumentAccessFactsReader(
                session, application_key_profile=application_key_profile
            )
        )

    async def create(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        name: ResourceName,
        display_name: SubmittedDisplayName,
        operation_id: OperationId,
    ) -> CollectionRevisionDTO:
        installation, organization = await self._lock_scope(access, project_id)
        facts = await self._action_facts.read_action_facts(
            access=access,
            action_id=ActionId(ProjectAction.CREATE_COLLECTIONS.value),
            target=ProjectActionTargetDTO(project_id=project_id),
        )
        if facts is None:
            raise ResourceNotFoundError()
        ActionAuthorizationService.require_authorization_from_facts(access=access, facts=facts)
        if facts.principal.kind is not PrincipalKind.HUMAN:
            raise AccessDeniedError()

        actor = access.actor_principal_id.value
        original = await self._original(operation_id)
        if original is not None:
            collection = await self._collection(
                installation, organization, project_id, original.collection_id
            )
            if (
                collection is None
                or not self._matches_original(original, collection, actor, base=None)
                or collection.name != name.value
                or collection.display_name != display_name.value
                or await self._version_ids(original.id)
            ):
                raise ConflictError("The original Collection creation does not match.")
            return CollectionRevisionDTO(
                collection_id=CollectionId(collection.id),
                revision_id=CollectionRevisionId(original.id),
                version_ids=(),
            )

        if await self._session.scalar(
            select(CollectionRow.id).where(
                CollectionRow.project_id == project_id.value, CollectionRow.name == name.value
            )
        ):
            raise ConflictError("The Collection name is already in use.")
        access_revision = await self._session.scalar(
            update(ProjectRow)
            .where(
                ProjectRow.id == project_id.value,
                ProjectRow.organization_id == organization,
                ProjectRow.access_revision < RevisionValidation.MAX_VALUE,
            )
            .values(access_revision=ProjectRow.access_revision + 1)
            .returning(ProjectRow.access_revision)
        )
        if access_revision is None:
            raise ConflictError("The Project access revision is exhausted.")
        collection = CollectionRow(
            id=uuid4(),
            installation_id=installation,
            organization_id=organization,
            project_id=project_id.value,
            name=name.value,
            display_name=display_name.value,
            current_revision_id=uuid4(),
        )
        self._session.add(collection)
        await self._session.flush()
        self._session.add(
            self._revision(collection, collection.current_revision_id, actor, operation_id)
        )
        self._session.add_all(
            CollectionActionGrantRow(
                project_id=project_id.value,
                collection_id=collection.id,
                recipient_principal_id=actor,
                action=action,
                recipient_kind=PrincipalKind.HUMAN,
                can_grant=True,
                assigned_by_principal_id=actor,
            )
            for action in _CREATOR_ACTIONS
        )
        self._session.add(
            AccessAuditEventRow(
                id=uuid4(),
                organization_id=organization,
                project_id=project_id.value,
                actor_kind=PrincipalKind.HUMAN.value,
                actor_principal_id=actor,
                event_type="collection_created",
                target_kind="collection",
                target_id=collection.id,
                correlation_id=operation_id.value,
                after_values={
                    "initial_actions": list(_CREATOR_ACTIONS),
                    "project_access_revision": access_revision,
                },
            )
        )
        await self._session.flush()
        return CollectionRevisionDTO(
            collection_id=CollectionId(collection.id),
            revision_id=CollectionRevisionId(collection.current_revision_id),
            version_ids=(),
        )

    async def select(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        collection_id: CollectionId,
        expected_base: CollectionRevisionId,
        version_ids: tuple[DocumentVersionId, ...],
        operation_id: OperationId,
    ) -> CollectionRevisionDTO:
        if len(version_ids) > _MAX_DOCUMENTS or len(set(version_ids)) != len(version_ids):
            raise InvalidInputError("Select at most 200 distinct Document versions.")
        canonical = tuple(sorted(version_ids, key=lambda version: version.value))
        installation, organization = await self._lock_scope(access, project_id)
        facts = await self._action_facts.read_scope_facts(
            access=access, target=ProjectActionTargetDTO(project_id=project_id)
        )
        if facts is None:
            raise ResourceNotFoundError()
        actor = access.actor_principal_id.value
        grant = CollectionActionGrantRow
        can_edit = await self._session.scalar(
            select(
                exists().where(
                    grant.project_id == project_id.value,
                    grant.collection_id == collection_id.value,
                    grant.recipient_principal_id == actor,
                    grant.recipient_kind == facts.principal.kind,
                    grant.action == _EDIT,
                )
            )
        )
        ActionAuthorizationService.require_authorization_from_facts(
            access=access, facts=replace(facts, has_exact_action_grant=bool(can_edit))
        )
        collection = await self._collection(
            installation, organization, project_id, collection_id.value
        )
        if collection is None:
            raise ResourceNotFoundError()

        original = await self._original(operation_id)
        if original is None and collection.current_revision_id != expected_base.value:
            raise StaleRevisionError()
        sources = await self._require_source_access(access, collection, canonical)
        if original is not None:
            if (
                not self._matches_original(original, collection, actor, base=expected_base.value)
                or await self._version_ids(original.id) != canonical
            ):
                raise ConflictError("The original Collection selection does not match.")
            return CollectionRevisionDTO(
                collection_id=collection_id,
                revision_id=CollectionRevisionId(original.id),
                version_ids=canonical,
            )

        revision = self._revision(
            collection, uuid4(), actor, operation_id, base=expected_base.value
        )
        self._session.add(revision)
        await self._session.flush()
        self._session.add_all(
            CollectionRevisionDocumentRow(
                collection_revision_id=revision.id,
                document_id=source.document_id.value,
                document_version_id=source.version_id.value,
                installation_id=installation,
                organization_id=organization,
                project_id=project_id.value,
            )
            for source in sources
        )
        collection.current_revision_id = revision.id
        evidence = access.authentication_evidence
        self._session.add(
            AccessAuditEventRow(
                id=uuid4(),
                organization_id=organization,
                project_id=project_id.value,
                actor_kind=facts.principal.kind.value,
                actor_principal_id=actor,
                actor_reference=(
                    str(evidence.key_id.value)
                    if isinstance(evidence, ApplicationKeyAuthenticationDTO)
                    else None
                ),
                event_type="collection_selection_changed",
                target_kind="collection",
                target_id=collection.id,
                correlation_id=operation_id.value,
                before_values={"revision_id": str(expected_base.value)},
                after_values={"revision_id": str(revision.id), "document_count": len(sources)},
            )
        )
        await self._session.flush()
        return CollectionRevisionDTO(
            collection_id=collection_id,
            revision_id=CollectionRevisionId(revision.id),
            version_ids=canonical,
        )

    async def require_reviewed_sources(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        collection_id: CollectionId,
        revision_id: CollectionRevisionId,
    ) -> tuple[DocumentSourceId, ...]:
        """Read a freshly reviewed selection under the same turn as its writes."""
        installation, organization = await self._lock_scope(access, project_id)
        collection = await self._collection(
            installation, organization, project_id, collection_id.value
        )
        if collection is None:
            raise ResourceNotFoundError()
        if collection.current_revision_id != revision_id.value:
            raise StaleRevisionError()
        grant = CollectionActionGrantRow
        facts = await self._action_facts.read_scope_facts(
            access=access, target=ProjectActionTargetDTO(project_id)
        )
        if facts is None:
            raise ResourceNotFoundError()
        can_view = await self._session.scalar(
            select(
                exists().where(
                    grant.project_id == project_id.value,
                    grant.collection_id == collection_id.value,
                    grant.recipient_principal_id == access.actor_principal_id.value,
                    grant.recipient_kind == facts.principal.kind,
                    grant.action == "view-collection",
                )
            )
        )
        ActionAuthorizationService.require_authorization_from_facts(
            access=access, facts=replace(facts, has_exact_action_grant=bool(can_view))
        )
        versions = await self._version_ids(revision_id.value)
        return await self._require_source_access(access, collection, versions)

    async def _lock_scope(self, access: AccessContextDTO, project: ProjectId) -> tuple[UUID, UUID]:
        try:
            async with asyncio.timeout(5):
                organization = await PostgresProjectScopeLock.acquire(
                    self._session, access.actor_principal_id, project, shared=False
                )
                if organization is None:
                    raise ResourceNotFoundError()
                installation = await self._session.scalar(
                    select(InstallationIdentityRow.installation_id).where(
                        InstallationIdentityRow.singleton_key == 1
                    )
                )
        except TimeoutError:
            raise DependencyUnavailableError() from None
        if installation is None:
            raise DependencyUnavailableError()
        return installation, organization

    async def _collection(
        self, installation: UUID, organization: UUID, project: ProjectId, collection: UUID
    ) -> CollectionRow | None:
        return await self._session.scalar(
            select(CollectionRow)
            .where(
                CollectionRow.id == collection,
                CollectionRow.installation_id == installation,
                CollectionRow.organization_id == organization,
                CollectionRow.project_id == project.value,
            )
            .execution_options(populate_existing=True)
        )

    async def _original(self, operation: OperationId) -> CollectionRevisionRow | None:
        return await self._session.scalar(
            select(CollectionRevisionRow).where(
                CollectionRevisionRow.operation_id == operation.value
            )
        )

    async def _version_ids(self, revision: UUID) -> tuple[DocumentVersionId, ...]:
        member = CollectionRevisionDocumentRow
        ids = await self._session.scalars(
            select(member.document_version_id)
            .where(member.collection_revision_id == revision)
            .order_by(member.document_version_id)
        )
        return tuple(DocumentVersionId(value) for value in ids)

    @staticmethod
    def _matches_original(
        original: CollectionRevisionRow,
        collection: CollectionRow,
        actor: UUID,
        *,
        base: UUID | None,
    ) -> bool:
        return (
            original.installation_id == collection.installation_id
            and original.organization_id == collection.organization_id
            and original.project_id == collection.project_id
            and original.collection_id == collection.id
            and original.actor_principal_id == actor
            and original.base_revision_id == base
        )

    @staticmethod
    def _revision(
        collection: CollectionRow,
        revision: UUID,
        actor: UUID,
        operation: OperationId,
        *,
        base: UUID | None = None,
    ) -> CollectionRevisionRow:
        return CollectionRevisionRow(
            id=revision,
            collection_id=collection.id,
            installation_id=collection.installation_id,
            organization_id=collection.organization_id,
            project_id=collection.project_id,
            base_revision_id=base,
            operation_id=operation.value,
            actor_principal_id=actor,
        )

    async def _require_source_access(
        self,
        access: AccessContextDTO,
        collection: CollectionRow,
        versions: tuple[DocumentVersionId, ...],
    ) -> tuple[DocumentSourceId, ...]:
        if not versions:
            return ()
        document, version, attempt = DocumentRow, DocumentVersionRow, ArtifactAttemptRow
        statement = (
            select(
                version.id,
                document.id,
                document.erasure_operation_id.is_(None) & document.erasure_blocked_at.is_(None),
            )
            .select_from(version)
            .join(
                document,
                and_(
                    document.id == version.document_id,
                    document.installation_id == version.installation_id,
                    document.organization_id == version.organization_id,
                    document.project_id == version.project_id,
                ),
            )
            .join(
                attempt,
                and_(
                    attempt.id == version.attempt_id,
                    attempt.installation_id == version.installation_id,
                    attempt.organization_id == version.organization_id,
                    attempt.project_id == version.project_id,
                    attempt.length == version.length,
                    attempt.digest == version.digest,
                ),
            )
            .where(
                version.id.in_(value.value for value in versions),
                version.installation_id == collection.installation_id,
                version.organization_id == collection.organization_id,
                version.project_id == collection.project_id,
                attempt.state == "published",
                attempt.published.is_(True),
                attempt.put_confirmed.is_(True),
                attempt.retired.is_(False),
                attempt.remote_removed.is_(False),
            )
            .order_by(document.id)
            .with_for_update(read=True, of=document)
        )
        try:
            async with asyncio.timeout(5):
                observations = (await self._session.execute(statement)).tuples().all()
        except TimeoutError:
            raise DependencyUnavailableError() from None
        if len(observations) != len(versions):
            raise AccessDeniedError()

        document_live = {
            DocumentId(document_id): is_live for _, document_id, is_live in observations
        }
        sources_by_version = {
            DocumentVersionId(version_id): DocumentId(document_id)
            for version_id, document_id, _ in observations
        }
        audiences: dict[DocumentId, set[AccessGroupId]] = {
            document_id: set() for document_id in document_live
        }
        groups = await self._session.execute(
            select(DocumentGroupRow.document_id, DocumentGroupRow.group_id).where(
                DocumentGroupRow.document_id.in_(value.value for value in document_live)
            )
        )
        for document_id, group_id in groups.tuples():
            audiences[DocumentId(document_id)].add(AccessGroupId(group_id))
        project = ProjectId(collection.project_id)
        permitted = await self._document_access.require_complete_evidence(
            access=access,
            project_id=project,
            selected=tuple(
                SelectedDocumentSourceDTO(
                    source_id=DocumentSourceId(sources_by_version[version_id], version_id),
                    is_live=True,
                )
                for version_id in versions
            ),
            documents=tuple(
                CurrentDocumentAccessDTO(
                    document_id=document_id,
                    project_id=project,
                    audience=frozenset(audiences[document_id]),
                    is_live=is_live,
                )
                for document_id, is_live in document_live.items()
            ),
        )
        if len(permitted) != len(document_live):
            raise ConflictError("Select at most one version of each Document.")
        return permitted
