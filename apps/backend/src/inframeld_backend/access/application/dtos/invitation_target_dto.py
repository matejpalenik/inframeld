from inframeld_backend.access.application.dtos.access_group_grant_target_dto import (
    AccessGroupGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.application_account_grant_target_dto import (
    ApplicationAccountGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.invitation_collection_target_dto import (
    InvitationCollectionTargetDTO,
)
from inframeld_backend.access.application.dtos.invitation_deployment_target_dto import (
    InvitationDeploymentTargetDTO,
)
from inframeld_backend.access.application.dtos.invitation_embedding_profile_target_dto import (
    InvitationEmbeddingProfileTargetDTO,
)
from inframeld_backend.access.application.dtos.invitation_model_connection_target_dto import (
    InvitationModelConnectionTargetDTO,
)
from inframeld_backend.access.application.dtos.invitation_pipeline_target_dto import (
    InvitationPipelineTargetDTO,
)
from inframeld_backend.access.application.dtos.invitation_processing_profile_target_dto import (
    InvitationProcessingProfileTargetDTO,
)
from inframeld_backend.access.application.dtos.invitation_source_target_dto import (
    InvitationSourceTargetDTO,
)
from inframeld_backend.access.application.dtos.organization_grant_target_dto import (
    OrganizationGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.project_grant_target_dto import (
    ProjectGrantTargetDTO,
)

# Receiving owners supply authoritative facts and a real transition for these closed shapes.
type InvitationTargetDTO = (
    OrganizationGrantTargetDTO
    | ProjectGrantTargetDTO
    | AccessGroupGrantTargetDTO
    | ApplicationAccountGrantTargetDTO
    | InvitationPipelineTargetDTO
    | InvitationDeploymentTargetDTO
    | InvitationCollectionTargetDTO
    | InvitationSourceTargetDTO
    | InvitationModelConnectionTargetDTO
    | InvitationProcessingProfileTargetDTO
    | InvitationEmbeddingProfileTargetDTO
)
