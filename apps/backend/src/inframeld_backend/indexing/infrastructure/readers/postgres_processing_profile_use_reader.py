from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.admitted_work_authority_dto import (
    AdmittedWorkAuthorityDTO,
)
from inframeld_backend.indexing.domain.enums.processing_profile_action import (
    ProcessingProfileAction,
)
from inframeld_backend.indexing.domain.value_objects.docling_processing_definition import (
    DoclingProcessingDefinition,
)
from inframeld_backend.indexing.domain.value_objects.processing_profile_id import (
    ProcessingProfileId,
)
from inframeld_backend.indexing.infrastructure.mappers.postgres_processing_profile_mapper import (
    PostgresProcessingProfileMapper,
)
from inframeld_backend.indexing.infrastructure.rows.processing_profile_action_grant_row import (
    ProcessingProfileActionGrantRow,
)
from inframeld_backend.indexing.infrastructure.rows.processing_profile_row import (
    ProcessingProfileRow,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
)


class PostgresProcessingProfileUseReader:
    """Read one exact saved profile after current admitted-work scope authorization."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def read(
        self, authority: AdmittedWorkAuthorityDTO, profile_id: ProcessingProfileId
    ) -> DoclingProcessingDefinition:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Processing Profile use requires the caller transaction.")

        profile = ProcessingProfileRow
        grant = ProcessingProfileActionGrantRow
        row = await self._session.scalar(
            select(profile)
            .where(
                profile.id == profile_id.value,
                profile.organization_id == authority.organization_id.value,
                profile.project_id == authority.project_id.value,
                exists().where(
                    grant.project_id == profile.project_id,
                    grant.processing_profile_id == profile.id,
                    grant.recipient_principal_id == authority.principal_id.value,
                    grant.recipient_kind == authority.principal_kind,
                    grant.action == ProcessingProfileAction.USE.value,
                ),
            )
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise AccessDeniedError("The original Processing Profile is unavailable.")
        try:
            definition = PostgresProcessingProfileMapper.profile(row).definition
        except (TypeError, ValueError):
            raise ConflictError("The saved Processing Profile cannot be prepared.") from None
        if definition.merge_peers or not definition.repeat_table_header:
            raise ConflictError("The saved Processing Profile cannot be prepared.")
        return definition
