from sqlalchemy import Nullable, and_, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.admitted_work_authority_dto import (
    AdmittedWorkAuthorityDTO,
)
from inframeld_backend.access.domain.policies.document_read_policy import DocumentReadPolicy
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.document_source_id import DocumentSourceId
from inframeld_backend.access.infrastructure.rows.access_group_row import AccessGroupRow
from inframeld_backend.access.infrastructure.rows.group_membership_row import GroupMembershipRow
from inframeld_backend.knowledge.infrastructure.readers.postgres_sealed_pdf_source_reader import (
    PostgresSealedPdfSourceReader,
)
from inframeld_backend.knowledge.infrastructure.rows.document_group_row import DocumentGroupRow
from inframeld_backend.knowledge.infrastructure.rows.document_version_row import DocumentVersionRow
from inframeld_backend.shared.application.dtos.artifact_attempt_dto import ArtifactAttemptDTO
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.errors.application_errors import AccessDeniedError


class PostgresAdmittedPdfSourceReader:
    """Require current access to the exact sealed source for admitted work.

    The caller holds current admitted-work authority in the same transaction.
    Publication also holds the Document turn through commit.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def read(
        self,
        authority: AdmittedWorkAuthorityDTO,
        source: DocumentSourceId,
        *,
        for_publication: bool = False,
    ) -> ArtifactAttemptDTO:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Admitted PDF source access requires the caller transaction.")

        scope = ArtifactScopeDTO(
            authority.installation_id, authority.organization_id, authority.project_id
        )
        source_reader = PostgresSealedPdfSourceReader(self._session)
        if for_publication:
            seal = await source_reader.read_for_publication(scope, source.version_id)
        else:
            seal = await source_reader.read(scope, source.version_id)
        if seal is None:
            raise AccessDeniedError("The original PDF source is unavailable.")

        groups, version = DocumentGroupRow, DocumentVersionRow
        member = (
            exists()
            .where(
                GroupMembershipRow.project_id == authority.project_id.value,
                GroupMembershipRow.group_id == groups.group_id,
                GroupMembershipRow.principal_id == authority.principal_id.value,
            )
            .correlate(groups)
        )
        rows = await self._session.execute(
            select(groups.group_id, Nullable(AccessGroupRow.id), member)
            .select_from(version)
            .join(groups, groups.document_id == version.document_id)
            .outerjoin(
                AccessGroupRow,
                and_(
                    AccessGroupRow.id == groups.group_id,
                    groups.project_id == version.project_id,
                    AccessGroupRow.project_id == version.project_id,
                ),
            )
            .where(
                version.id == source.version_id.value,
                version.document_id == source.document_id.value,
                version.installation_id == authority.installation_id.value,
                version.organization_id == authority.organization_id.value,
                version.project_id == authority.project_id.value,
            )
        )
        observations = rows.tuples().all()
        if not DocumentReadPolicy.may_read(
            requested_project_id=authority.project_id,
            document_project_id=seal.scope.project_id,
            source_is_live=True,
            document_is_live=True,
            audience=frozenset(AccessGroupId(group_id) for group_id, _, _ in observations),
            valid_group_ids=frozenset(
                AccessGroupId(group_id) for _, group_id, _ in observations if group_id is not None
            ),
            member_group_ids=frozenset(
                AccessGroupId(group_id) for group_id, _, is_member in observations if is_member
            ),
        ):
            raise AccessDeniedError("The original PDF source is unavailable.")
        return seal
