from typing import override

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.current_document_access_dto import (
    CurrentDocumentAccessDTO,
)
from inframeld_backend.access.application.dtos.selected_document_source_dto import (
    SelectedDocumentSourceDTO,
)
from inframeld_backend.access.application.protocols.document_access_authorizer import (
    DocumentAccessAuthorizer,
)
from inframeld_backend.access.application.protocols.document_access_facts_reader import (
    DocumentAccessFactsReader,
)
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.domain.policies.document_read_policy import DocumentReadPolicy
from inframeld_backend.access.domain.policies.principal_access_policy import PrincipalAccessPolicy
from inframeld_backend.access.domain.policies.project_visibility_policy import (
    ProjectVisibilityPolicy,
)
from inframeld_backend.access.domain.value_objects.document_id import DocumentId
from inframeld_backend.access.domain.value_objects.document_source_id import DocumentSourceId
from inframeld_backend.access.domain.value_objects.document_version_id import DocumentVersionId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    DependencyUnavailableError,
    ResourceNotFoundError,
)


class DocumentAccessService(DocumentAccessAuthorizer):
    def __init__(self, facts_reader: DocumentAccessFactsReader) -> None:
        self._facts_reader = facts_reader

    @override
    async def permitted_sources(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        selected: tuple[SelectedDocumentSourceDTO, ...],
        documents: tuple[CurrentDocumentAccessDTO, ...],
    ) -> tuple[DocumentSourceId, ...]:
        facts = await self._facts_reader.read(
            access=access,
            project_id=project_id,
            audience_group_ids=frozenset(
                group for document in documents for group in document.audience
            ),
        )
        if facts is None:
            raise ResourceNotFoundError()
        if (
            facts.principal.id != access.actor_principal_id
            or facts.project_id != project_id
            or facts.principal.organization_id != facts.organization_id
        ):
            raise RuntimeError("Document facts changed the requested actor or scope.")
        principal_access = PrincipalAccessEvaluationService.evaluate(
            access=access,
            principal=facts.principal,
            has_pending_recovery=facts.has_pending_recovery,
            oauth_credential_facts=facts.oauth_credential_facts,
            application_key_facts=facts.application_key_facts,
        )
        PrincipalAccessEvaluationService.require_current_credential(
            access=access, principal_access=principal_access
        )
        if not ProjectVisibilityPolicy.may_view_project(
            principal_status=facts.principal.status,
            project_status=facts.project_status,
            is_project_member=facts.is_project_member,
        ):
            raise ResourceNotFoundError()
        if not PrincipalAccessPolicy.may_use_product(principal_access):
            raise AccessDeniedError()
        current: dict[DocumentId, CurrentDocumentAccessDTO] = {}
        for document in documents:
            if document.document_id in current and current[document.document_id] != document:
                raise RuntimeError("Conflicting current Document observations.")
            current[document.document_id] = document
        versions: dict[DocumentVersionId, DocumentId] = {}
        sources: dict[DocumentSourceId, SelectedDocumentSourceDTO] = {}
        permitted: list[DocumentSourceId] = []
        for source in selected:
            identity = source.source_id
            if (
                identity.version_id in versions
                and versions[identity.version_id] != identity.document_id
                or identity in sources
                and sources[identity] != source
            ):
                raise RuntimeError("Conflicting selected source observations.")
            versions[identity.version_id] = identity.document_id
            sources[identity] = source
            document = current.get(identity.document_id)
            if document is None:
                raise DependencyUnavailableError()
            if DocumentReadPolicy.may_read(
                requested_project_id=project_id,
                document_project_id=document.project_id,
                source_is_live=source.is_live,
                document_is_live=document.is_live,
                audience=document.audience,
                valid_group_ids=facts.valid_group_ids,
                member_group_ids=facts.member_group_ids,
            ):
                permitted.append(identity)
        return tuple(permitted)

    @override
    async def require_complete_evidence(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        selected: tuple[SelectedDocumentSourceDTO, ...],
        documents: tuple[CurrentDocumentAccessDTO, ...],
    ) -> tuple[DocumentSourceId, ...]:
        permitted = await self.permitted_sources(
            access=access, project_id=project_id, selected=selected, documents=documents
        )
        if len(permitted) != len(selected):
            raise AccessDeniedError()
        return permitted
