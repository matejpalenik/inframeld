from typing import Annotated

from pydantic import Field

from inframeld_backend.access.http.requests.invitation_access_group_target_request import (
    InvitationAccessGroupTargetRequest,
)
from inframeld_backend.access.http.requests.invitation_application_account_target_request import (
    InvitationApplicationAccountTargetRequest,
)
from inframeld_backend.access.http.requests.invitation_collection_target_request import (
    InvitationCollectionTargetRequest,
)
from inframeld_backend.access.http.requests.invitation_deployment_target_request import (
    InvitationDeploymentTargetRequest,
)
from inframeld_backend.access.http.requests.invitation_embedding_profile_target_request import (
    InvitationEmbeddingProfileTargetRequest,
)
from inframeld_backend.access.http.requests.invitation_model_connection_target_request import (
    InvitationModelConnectionTargetRequest,
)
from inframeld_backend.access.http.requests.invitation_organization_target_request import (
    InvitationOrganizationTargetRequest,
)
from inframeld_backend.access.http.requests.invitation_pipeline_target_request import (
    InvitationPipelineTargetRequest,
)
from inframeld_backend.access.http.requests.invitation_processing_profile_target_request import (
    InvitationProcessingProfileTargetRequest,
)
from inframeld_backend.access.http.requests.invitation_project_target_request import (
    InvitationProjectTargetRequest,
)
from inframeld_backend.access.http.requests.invitation_source_target_request import (
    InvitationSourceTargetRequest,
)

type InvitationTargetRequest = Annotated[
    InvitationOrganizationTargetRequest
    | InvitationProjectTargetRequest
    | InvitationAccessGroupTargetRequest
    | InvitationApplicationAccountTargetRequest
    | InvitationPipelineTargetRequest
    | InvitationDeploymentTargetRequest
    | InvitationCollectionTargetRequest
    | InvitationSourceTargetRequest
    | InvitationModelConnectionTargetRequest
    | InvitationProcessingProfileTargetRequest
    | InvitationEmbeddingProfileTargetRequest,
    Field(discriminator="kind"),
]
