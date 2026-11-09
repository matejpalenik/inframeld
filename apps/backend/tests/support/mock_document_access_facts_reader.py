from typing import override

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.document_access_facts_dto import (
    DocumentAccessFactsDTO,
)
from inframeld_backend.access.application.protocols.document_access_facts_reader import (
    DocumentAccessFactsReader,
)
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


class MockDocumentAccessFactsReader(DocumentAccessFactsReader):
    def __init__(self, facts: DocumentAccessFactsDTO | None) -> None:
        self.facts = facts
        self.calls: list[tuple[AccessContextDTO, ProjectId, frozenset[AccessGroupId]]] = []

    @override
    async def read(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        audience_group_ids: frozenset[AccessGroupId],
    ) -> DocumentAccessFactsDTO | None:
        self.calls.append((access, project_id, audience_group_ids))
        return self.facts
