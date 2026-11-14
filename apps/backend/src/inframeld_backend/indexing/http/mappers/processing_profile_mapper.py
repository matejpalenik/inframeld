from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.indexing.application.commands.create_processing_profile_command import (
    CreateProcessingProfileCommand,
)
from inframeld_backend.indexing.application.dtos.processing_profile_creation_dto import (
    ProcessingProfileCreationDTO,
)
from inframeld_backend.indexing.application.dtos.processing_profile_dto import ProcessingProfileDTO
from inframeld_backend.indexing.domain.value_objects.docling_processing_definition import (
    DoclingProcessingDefinition,
)
from inframeld_backend.indexing.http.enums.processing_profile_target_kind import (
    ProcessingProfileTargetKind,
)
from inframeld_backend.indexing.http.requests.processing_profile_creation_request import (
    ProcessingProfileCreationRequest,
)
from inframeld_backend.indexing.http.responses.docling_processing_definition_response import (
    DoclingProcessingDefinitionResponse,
)
from inframeld_backend.indexing.http.responses.initial_processing_profile_grant_response import (
    InitialProcessingProfileGrantResponse,
)
from inframeld_backend.indexing.http.responses.processing_profile_creation_response import (
    ProcessingProfileCreationResponse,
)
from inframeld_backend.indexing.http.responses.processing_profile_grant_target_response import (
    ProcessingProfileGrantTargetResponse,
)
from inframeld_backend.indexing.http.responses.processing_profile_response import (
    ProcessingProfileResponse,
)
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)


class ProcessingProfileMapper:
    @staticmethod
    def command(
        project_id: ProjectId, body: ProcessingProfileCreationRequest
    ) -> CreateProcessingProfileCommand:
        definition = body.definition
        return CreateProcessingProfileCommand(
            project_id=project_id,
            name=ResourceName(body.name),
            display_name=SubmittedDisplayName(body.display_name),
            definition=DoclingProcessingDefinition(
                docling_slim_version=definition.docling_slim_version,
                docling_core_version=definition.docling_core_version,
                asset_manifest_sha256=definition.asset_manifest_sha256,
                max_content_tokens=definition.max_content_tokens,
                merge_peers=definition.merge_peers,
                repeat_table_header=definition.repeat_table_header,
                ocr_enabled=definition.ocr_enabled,
            ),
        )

    @staticmethod
    def profile(profile: ProcessingProfileDTO) -> ProcessingProfileResponse:
        definition = profile.definition
        return ProcessingProfileResponse(
            project_id=profile.project_id.value,
            processing_profile_id=profile.id.value,
            name=profile.name.value,
            display_name=profile.display_name.value,
            definition=DoclingProcessingDefinitionResponse(
                docling_slim_version=definition.docling_slim_version,
                docling_core_version=definition.docling_core_version,
                asset_manifest_sha256=definition.asset_manifest_sha256,
                max_content_tokens=definition.max_content_tokens,
                merge_peers=definition.merge_peers,
                repeat_table_header=definition.repeat_table_header,
                ocr_enabled=definition.ocr_enabled,
            ),
        )

    @staticmethod
    def creation(result: ProcessingProfileCreationDTO) -> ProcessingProfileCreationResponse:
        target = ProcessingProfileGrantTargetResponse(
            kind=ProcessingProfileTargetKind.PROCESSING_PROFILE,
            processing_profile_id=result.profile.id.value,
        )
        return ProcessingProfileCreationResponse(
            profile=ProcessingProfileMapper.profile(result.profile),
            operation_id=result.operation.operation_id.value,
            idempotency_expires_at=result.operation.expires_at,
            project_access_revision=result.project_access_revision,
            initial_grants=tuple(
                InitialProcessingProfileGrantResponse(
                    target=target, action_id=action, can_grant=result.can_grant
                )
                for action in result.initial_actions
            ),
        )
