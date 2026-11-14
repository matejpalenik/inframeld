from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.indexing.application.dtos.processing_profile_dto import ProcessingProfileDTO
from inframeld_backend.indexing.domain.value_objects.docling_processing_definition import (
    DoclingProcessingDefinition,
)
from inframeld_backend.indexing.domain.value_objects.processing_profile_id import (
    ProcessingProfileId,
)
from inframeld_backend.indexing.infrastructure.rows.processing_profile_row import (
    ProcessingProfileRow,
)
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)


class PostgresProcessingProfileMapper:
    @staticmethod
    def profile(row: ProcessingProfileRow) -> ProcessingProfileDTO:
        if row.ocr_enabled:
            raise ValueError("The stored Processing Profile enables unsupported OCR.")

        return ProcessingProfileDTO(
            project_id=ProjectId(row.project_id),
            id=ProcessingProfileId(row.id),
            name=ResourceName(row.name),
            display_name=SubmittedDisplayName(row.display_name),
            definition=DoclingProcessingDefinition(
                docling_slim_version=row.docling_slim_version,
                docling_core_version=row.docling_core_version,
                asset_manifest_sha256=row.asset_manifest_sha256,
                max_content_tokens=row.max_content_tokens,
                merge_peers=row.merge_peers,
                repeat_table_header=row.repeat_table_header,
                ocr_enabled=False,
            ),
        )
