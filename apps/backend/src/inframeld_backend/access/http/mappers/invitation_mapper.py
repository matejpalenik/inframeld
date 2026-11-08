from uuid import UUID

from inframeld_backend.access.application.commands.activate_invitation_command import (
    ActivateInvitationCommand,
)
from inframeld_backend.access.application.commands.issue_invitation_command import (
    IssueInvitationCommand,
)
from inframeld_backend.access.application.commands.revoke_invitation_command import (
    RevokeInvitationCommand,
)
from inframeld_backend.access.application.dtos.access_group_grant_target_dto import (
    AccessGroupGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.application_account_grant_target_dto import (
    ApplicationAccountGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.invitation_action_grant_intent_dto import (
    InvitationActionGrantIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_activation_result_dto import (
    InvitationActivationResultDTO,
)
from inframeld_backend.access.application.dtos.invitation_admission_only_intent_dto import (
    InvitationAdmissionOnlyIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_assignment_dto import (
    InvitationAssignmentDTO,
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
from inframeld_backend.access.application.dtos.invitation_group_manager_intent_dto import (
    InvitationGroupManagerIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_group_membership_intent_dto import (
    InvitationGroupMembershipIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_issue_result_dto import (
    InvitationIssueResultDTO,
)
from inframeld_backend.access.application.dtos.invitation_model_connection_target_dto import (
    InvitationModelConnectionTargetDTO,
)
from inframeld_backend.access.application.dtos.invitation_pipeline_target_dto import (
    InvitationPipelineTargetDTO,
)
from inframeld_backend.access.application.dtos.invitation_preview_result_dto import (
    InvitationPreviewResultDTO,
)
from inframeld_backend.access.application.dtos.invitation_processing_profile_target_dto import (
    InvitationProcessingProfileTargetDTO,
)
from inframeld_backend.access.application.dtos.invitation_project_access_revision_dto import (
    InvitationProjectAccessRevisionDTO,
)
from inframeld_backend.access.application.dtos.invitation_project_membership_intent_dto import (
    InvitationProjectMembershipIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_revocation_result_dto import (
    InvitationRevocationResultDTO,
)
from inframeld_backend.access.application.dtos.invitation_source_target_dto import (
    InvitationSourceTargetDTO,
)
from inframeld_backend.access.application.dtos.invitation_target_dto import InvitationTargetDTO
from inframeld_backend.access.application.dtos.organization_grant_target_dto import (
    OrganizationGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.project_grant_target_dto import ProjectGrantTargetDTO
from inframeld_backend.access.application.queries.preview_invitation_query import (
    PreviewInvitationQuery,
)
from inframeld_backend.access.domain.enums.invitation_assignment_kind import (
    InvitationAssignmentKind,
)
from inframeld_backend.access.domain.enums.invitation_target_kind import InvitationTargetKind
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.invitation_id import InvitationId
from inframeld_backend.access.domain.value_objects.invitation_token import InvitationToken
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.requests.invitation_access_group_target_request import (
    InvitationAccessGroupTargetRequest,
)
from inframeld_backend.access.http.requests.invitation_action_grant_request import (
    InvitationActionGrantRequest,
)
from inframeld_backend.access.http.requests.invitation_admission_only_request import (
    InvitationAdmissionOnlyRequest,
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
from inframeld_backend.access.http.requests.invitation_group_manager_request import (
    InvitationGroupManagerRequest,
)
from inframeld_backend.access.http.requests.invitation_group_membership_request import (
    InvitationGroupMembershipRequest,
)
from inframeld_backend.access.http.requests.invitation_issue_request import InvitationIssueRequest
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
from inframeld_backend.access.http.requests.invitation_project_membership_request import (
    InvitationProjectMembershipRequest,
)
from inframeld_backend.access.http.requests.invitation_project_target_request import (
    InvitationProjectTargetRequest,
)
from inframeld_backend.access.http.requests.invitation_revocation_request import (
    InvitationRevocationRequest,
)
from inframeld_backend.access.http.requests.invitation_source_target_request import (
    InvitationSourceTargetRequest,
)
from inframeld_backend.access.http.responses.invitation_activation_response import (
    InvitationActivationResponse,
)
from inframeld_backend.access.http.responses.invitation_first_delivery_response import (
    InvitationFirstDeliveryResponse,
)
from inframeld_backend.access.http.responses.invitation_issuance_replay_response import (
    InvitationIssuanceReplayResponse,
)
from inframeld_backend.access.http.responses.invitation_issue_response import (
    InvitationIssueResponse,
)
from inframeld_backend.access.http.responses.invitation_preview_response import (
    InvitationPreviewResponse,
)
from inframeld_backend.access.http.responses.invitation_project_access_revision_response import (
    InvitationProjectAccessRevisionResponse,
)
from inframeld_backend.access.http.responses.invitation_revocation_response import (
    InvitationRevocationResponse,
)
from inframeld_backend.access.http.responses.invitation_scope_response import (
    InvitationScopeResponse,
)
from inframeld_backend.access.http.types.invitation_assignment_request import (
    InvitationAssignmentRequest,
)
from inframeld_backend.access.http.types.invitation_target_request import InvitationTargetRequest
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.errors.application_errors import ResourceNotFoundError
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey


class InvitationMapper:
    """Translate exact invitation intent and safe workflow outcomes at the HTTP boundary."""

    @staticmethod
    def context(route: str, key: IdempotencyKey) -> IdempotencyContextDTO:
        return IdempotencyContextDTO(HttpMethod.POST, route, key)

    @staticmethod
    def token(value: str) -> InvitationToken:
        try:
            return InvitationToken(value)
        except ValueError:
            raise ResourceNotFoundError() from None

    @staticmethod
    def issue_command(body: InvitationIssueRequest) -> IssueInvitationCommand:
        return IssueInvitationCommand(
            OrganizationId(body.organization_id),
            tuple(InvitationMapper.assignment(item) for item in body.assignments),
            body.expected_access_revision,
            tuple(
                InvitationProjectAccessRevisionDTO(ProjectId(item.project_id), item.access_revision)
                for item in body.expected_project_access_revisions
            ),
            body.expires_in_seconds,
        )

    @staticmethod
    def revoke_command(
        invitation_id: UUID, body: InvitationRevocationRequest
    ) -> RevokeInvitationCommand:
        return RevokeInvitationCommand(InvitationId(invitation_id), body.expected_access_revision)

    @staticmethod
    def preview_query(value: str) -> PreviewInvitationQuery:
        return PreviewInvitationQuery(InvitationMapper.token(value))

    @staticmethod
    def activate_command(value: str) -> ActivateInvitationCommand:
        return ActivateInvitationCommand(InvitationMapper.token(value))

    @staticmethod
    def assignment(item: InvitationAssignmentRequest) -> InvitationAssignmentDTO:
        match item:
            case InvitationAdmissionOnlyRequest():
                return InvitationAdmissionOnlyIntentDTO()
            case InvitationProjectMembershipRequest():
                return InvitationProjectMembershipIntentDTO(ProjectId(item.project_id))
            case InvitationGroupMembershipRequest():
                return InvitationGroupMembershipIntentDTO(
                    ProjectId(item.project_id), AccessGroupId(item.access_group_id)
                )
            case InvitationGroupManagerRequest():
                return InvitationGroupManagerIntentDTO(
                    ProjectId(item.project_id), AccessGroupId(item.access_group_id)
                )
            case InvitationActionGrantRequest():
                return InvitationActionGrantIntentDTO(
                    InvitationMapper.target(item.target), ActionId(item.action_id), item.can_grant
                )

    @staticmethod
    def target(item: InvitationTargetRequest) -> InvitationTargetDTO:
        match item:
            case InvitationOrganizationTargetRequest():
                return OrganizationGrantTargetDTO(OrganizationId(item.organization_id))
            case InvitationProjectTargetRequest():
                return ProjectGrantTargetDTO(ProjectId(item.project_id))
            case InvitationAccessGroupTargetRequest():
                return AccessGroupGrantTargetDTO(
                    ProjectId(item.project_id), AccessGroupId(item.access_group_id)
                )
            case InvitationApplicationAccountTargetRequest():
                return ApplicationAccountGrantTargetDTO(
                    ProjectId(item.project_id), PrincipalId(item.application_principal_id)
                )
            case InvitationPipelineTargetRequest():
                return InvitationPipelineTargetDTO(item.pipeline_id)
            case InvitationDeploymentTargetRequest():
                return InvitationDeploymentTargetDTO(item.deployment_id)
            case InvitationCollectionTargetRequest():
                return InvitationCollectionTargetDTO(item.collection_id)
            case InvitationSourceTargetRequest():
                return InvitationSourceTargetDTO(item.source_id)
            case InvitationModelConnectionTargetRequest():
                return InvitationModelConnectionTargetDTO(item.model_connection_id)
            case InvitationProcessingProfileTargetRequest():
                return InvitationProcessingProfileTargetDTO(item.processing_profile_id)
            case InvitationEmbeddingProfileTargetRequest():
                return InvitationEmbeddingProfileTargetDTO(item.embedding_profile_id)

    @staticmethod
    def assignment_response(item: InvitationAssignmentDTO) -> InvitationAssignmentRequest:
        match item:
            case InvitationAdmissionOnlyIntentDTO():
                return InvitationAdmissionOnlyRequest(kind=InvitationAssignmentKind.ADMISSION_ONLY)
            case InvitationProjectMembershipIntentDTO():
                return InvitationProjectMembershipRequest(
                    kind=InvitationAssignmentKind.PROJECT_MEMBERSHIP,
                    projectId=item.project_id.value,
                )
            case InvitationGroupMembershipIntentDTO():
                return InvitationGroupMembershipRequest(
                    kind=InvitationAssignmentKind.GROUP_MEMBERSHIP,
                    projectId=item.project_id.value,
                    accessGroupId=item.access_group_id.value,
                )
            case InvitationGroupManagerIntentDTO():
                return InvitationGroupManagerRequest(
                    kind=InvitationAssignmentKind.GROUP_MANAGER,
                    projectId=item.project_id.value,
                    accessGroupId=item.access_group_id.value,
                )
            case InvitationActionGrantIntentDTO():
                return InvitationActionGrantRequest(
                    kind=InvitationAssignmentKind.ACTION_GRANT,
                    target=InvitationMapper.target_response(item.target),
                    actionId=item.action_id.value,
                    canGrant=item.can_grant,
                )

    @staticmethod
    def target_response(item: InvitationTargetDTO) -> InvitationTargetRequest:
        match item:
            case OrganizationGrantTargetDTO():
                return InvitationOrganizationTargetRequest(
                    kind=InvitationTargetKind.ORGANIZATION,
                    organizationId=item.organization_id.value,
                )
            case ProjectGrantTargetDTO():
                return InvitationProjectTargetRequest(
                    kind=InvitationTargetKind.PROJECT, projectId=item.project_id.value
                )
            case AccessGroupGrantTargetDTO():
                return InvitationAccessGroupTargetRequest(
                    kind=InvitationTargetKind.ACCESS_GROUP,
                    projectId=item.project_id.value,
                    accessGroupId=item.access_group_id.value,
                )
            case ApplicationAccountGrantTargetDTO():
                return InvitationApplicationAccountTargetRequest(
                    kind=InvitationTargetKind.APPLICATION_ACCOUNT,
                    projectId=item.project_id.value,
                    applicationPrincipalId=item.application_principal_id.value,
                )
            case InvitationPipelineTargetDTO():
                return InvitationPipelineTargetRequest(
                    kind=InvitationTargetKind.PIPELINE, pipelineId=item.pipeline_id
                )
            case InvitationDeploymentTargetDTO():
                return InvitationDeploymentTargetRequest(
                    kind=InvitationTargetKind.DEPLOYMENT, deploymentId=item.deployment_id
                )
            case InvitationCollectionTargetDTO():
                return InvitationCollectionTargetRequest(
                    kind=InvitationTargetKind.COLLECTION, collectionId=item.collection_id
                )
            case InvitationSourceTargetDTO():
                return InvitationSourceTargetRequest(
                    kind=InvitationTargetKind.SOURCE, sourceId=item.source_id
                )
            case InvitationModelConnectionTargetDTO():
                return InvitationModelConnectionTargetRequest(
                    kind=InvitationTargetKind.MODEL_CONNECTION,
                    modelConnectionId=item.model_connection_id,
                )
            case InvitationProcessingProfileTargetDTO():
                return InvitationProcessingProfileTargetRequest(
                    kind=InvitationTargetKind.PROCESSING_PROFILE,
                    processingProfileId=item.processing_profile_id,
                )
            case InvitationEmbeddingProfileTargetDTO():
                return InvitationEmbeddingProfileTargetRequest(
                    kind=InvitationTargetKind.EMBEDDING_PROFILE,
                    embeddingProfileId=item.embedding_profile_id,
                )

    @staticmethod
    def issue_response(result: InvitationIssueResultDTO) -> InvitationIssueResponse:
        assignments = [InvitationMapper.assignment_response(item) for item in result.assignments]
        if result.token is not None:
            return InvitationIssueResponse(
                InvitationFirstDeliveryResponse(
                    operation_id=result.operation.operation_id.value,
                    idempotency_expires_at=result.operation.expires_at,
                    invitation_id=result.invitation_id.value,
                    organization_id=result.organization_id.value,
                    assignments=assignments,
                    expires_at=result.expires_at,
                    access_revision=result.access_revision,
                    secretAvailable=True,
                    invitation_token=result.token.value,
                )
            )
        return InvitationIssueResponse(
            InvitationIssuanceReplayResponse(
                operation_id=result.operation.operation_id.value,
                idempotency_expires_at=result.operation.expires_at,
                invitation_id=result.invitation_id.value,
                organization_id=result.organization_id.value,
                assignments=assignments,
                expires_at=result.expires_at,
                access_revision=result.access_revision,
                secretAvailable=False,
            )
        )

    @staticmethod
    def revoke_response(result: InvitationRevocationResultDTO) -> InvitationRevocationResponse:
        return InvitationRevocationResponse(
            operation_id=result.operation.operation_id.value,
            idempotency_expires_at=result.operation.expires_at,
            invitation_id=result.invitation_id.value,
            organization_id=result.organization_id.value,
            access_revision=result.access_revision,
        )

    @staticmethod
    def preview_response(result: InvitationPreviewResultDTO) -> InvitationPreviewResponse:
        return InvitationPreviewResponse(
            invitation_id=result.invitation_id.value,
            organization_id=result.organization_id.value,
            assignments=[InvitationMapper.assignment_response(item) for item in result.assignments],
            expires_at=result.expires_at,
            scopes=[
                InvitationScopeResponse(
                    target=InvitationMapper.target_response(item.target),
                    display_name=item.display_name,
                )
                for item in result.scopes
            ],
        )

    @staticmethod
    def activate_response(result: InvitationActivationResultDTO) -> InvitationActivationResponse:
        return InvitationActivationResponse(
            operation_id=result.operation.operation_id.value,
            invitation_id=result.invitation_id.value,
            organization_id=result.organization_id.value,
            principal_id=result.principal_id.value,
            organization_access_revision=result.organization_access_revision,
            project_access_revisions=[
                InvitationProjectAccessRevisionResponse(
                    project_id=item.project_id.value, access_revision=item.access_revision
                )
                for item in result.project_access_revisions
            ],
            idempotency_expires_at=result.operation.expires_at,
        )
