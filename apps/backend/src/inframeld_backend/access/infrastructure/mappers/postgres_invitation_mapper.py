from typing import cast
from uuid import UUID

from inframeld_backend.access.application.dtos.access_group_grant_target_dto import (
    AccessGroupGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.application_account_grant_target_dto import (
    ApplicationAccountGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.invitation_action_grant_intent_dto import (
    InvitationActionGrantIntentDTO,
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
from inframeld_backend.access.application.dtos.invitation_model_connection_target_dto import (
    InvitationModelConnectionTargetDTO,
)
from inframeld_backend.access.application.dtos.invitation_pipeline_target_dto import (
    InvitationPipelineTargetDTO,
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
from inframeld_backend.access.application.dtos.invitation_source_target_dto import (
    InvitationSourceTargetDTO,
)
from inframeld_backend.access.application.dtos.invitation_target_dto import InvitationTargetDTO
from inframeld_backend.access.application.dtos.organization_grant_target_dto import (
    OrganizationGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.project_grant_target_dto import ProjectGrantTargetDTO
from inframeld_backend.access.domain.enums.invitation_assignment_kind import (
    InvitationAssignmentKind,
)
from inframeld_backend.access.domain.enums.invitation_target_kind import InvitationTargetKind
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class PostgresInvitationMapper:
    """Convert closed typed intent to JSONB without deciding authority or target existence."""

    @staticmethod
    def to_project_revisions(
        revisions: tuple[InvitationProjectAccessRevisionDTO, ...],
    ) -> list[dict[str, object]]:
        payload: list[dict[str, object]] = [
            {"projectId": str(item.project_id.value), "accessRevision": item.access_revision}
            for item in revisions
        ]
        PostgresInvitationMapper.from_project_revisions(payload)
        return payload

    @staticmethod
    def from_project_revisions(payload: object) -> tuple[InvitationProjectAccessRevisionDTO, ...]:
        if not isinstance(payload, list):
            raise TypeError("Stored activation revisions require an array.")
        items = cast(list[object], payload)
        if len(items) > 100:
            raise ValueError("Stored activation revisions exceed the intent bound.")
        revisions: list[InvitationProjectAccessRevisionDTO] = []
        seen: set[ProjectId] = set()
        for item in items:
            fields = PostgresInvitationMapper._fields(item, {"projectId", "accessRevision"})
            project = ProjectId(PostgresInvitationMapper._uuid(fields, "projectId"))
            revision = fields["accessRevision"]
            if type(revision) is not int:
                raise TypeError("Stored activation revisions require whole numbers.")
            RevisionValidation.require(revision)
            if revision < 1 or project in seen:
                raise ValueError("Stored activation revisions have invalid or duplicate Projects.")
            seen.add(project)
            revisions.append(
                InvitationProjectAccessRevisionDTO(project_id=project, access_revision=revision)
            )
        return tuple(revisions)

    @staticmethod
    def to_payload(assignments: tuple[InvitationAssignmentDTO, ...]) -> list[dict[str, object]]:
        payload: list[dict[str, object]] = []
        for intent in assignments:
            if isinstance(intent, InvitationAdmissionOnlyIntentDTO):
                payload.append({"kind": intent.kind.value})
            elif isinstance(intent, InvitationProjectMembershipIntentDTO):
                payload.append(
                    {"kind": intent.kind.value, "projectId": str(intent.project_id.value)}
                )
            elif isinstance(
                intent, (InvitationGroupMembershipIntentDTO, InvitationGroupManagerIntentDTO)
            ):
                payload.append(
                    {
                        "kind": intent.kind.value,
                        "projectId": str(intent.project_id.value),
                        "accessGroupId": str(intent.access_group_id.value),
                    }
                )
            else:
                payload.append(
                    {
                        "kind": intent.kind.value,
                        "target": PostgresInvitationMapper._target_payload(intent.target),
                        "actionId": intent.action_id.value,
                        "canGrant": intent.can_grant,
                    }
                )
        return payload

    @staticmethod
    def from_payload(payload: object) -> tuple[InvitationAssignmentDTO, ...]:
        """Reject malformed stored representations rather than silently dropping intent."""
        if not isinstance(payload, list):
            raise TypeError("Stored invitation intent must be an array.")
        items = cast(list[object], payload)
        if not 1 <= len(items) <= 100:
            raise ValueError("Stored invitation intent has an invalid size.")
        return tuple(PostgresInvitationMapper._assignment(item) for item in items)

    @staticmethod
    def _fields(payload: object, expected: set[str] | None = None) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise TypeError("Stored invitation intent requires an object.")
        # Dictionaries are confined to this JSONB conversion boundary.
        fields = cast(dict[str, object], payload)
        if expected is not None and fields.keys() != expected:
            raise ValueError("Stored invitation intent has unexpected fields.")
        return fields

    @staticmethod
    def _uuid(fields: dict[str, object], name: str) -> UUID:
        value = fields[name]
        if not isinstance(value, str):
            raise TypeError("A stored target requires a UUID string.")
        return UUID(value)

    @staticmethod
    def _assignment(payload: object) -> InvitationAssignmentDTO:
        fields = PostgresInvitationMapper._fields(payload)
        kind = InvitationAssignmentKind(fields.get("kind"))
        if kind is InvitationAssignmentKind.ADMISSION_ONLY:
            PostgresInvitationMapper._fields(fields, {"kind"})
            return InvitationAdmissionOnlyIntentDTO()
        if kind is InvitationAssignmentKind.PROJECT_MEMBERSHIP:
            PostgresInvitationMapper._fields(fields, {"kind", "projectId"})
            return InvitationProjectMembershipIntentDTO(
                project_id=ProjectId(PostgresInvitationMapper._uuid(fields, "projectId"))
            )
        if kind in {
            InvitationAssignmentKind.GROUP_MEMBERSHIP,
            InvitationAssignmentKind.GROUP_MANAGER,
        }:
            PostgresInvitationMapper._fields(fields, {"kind", "projectId", "accessGroupId"})
            project = ProjectId(PostgresInvitationMapper._uuid(fields, "projectId"))
            group = AccessGroupId(PostgresInvitationMapper._uuid(fields, "accessGroupId"))
            if kind is InvitationAssignmentKind.GROUP_MANAGER:
                return InvitationGroupManagerIntentDTO(project_id=project, access_group_id=group)
            return InvitationGroupMembershipIntentDTO(project_id=project, access_group_id=group)

        PostgresInvitationMapper._fields(fields, {"kind", "target", "actionId", "canGrant"})
        action, level = fields["actionId"], fields["canGrant"]
        if not isinstance(action, str) or type(level) is not bool:
            raise TypeError("A stored grant requires an action string and boolean level.")
        return InvitationActionGrantIntentDTO(
            target=PostgresInvitationMapper._target(fields["target"]),
            action_id=ActionId(action),
            can_grant=level,
        )

    @staticmethod
    def _target(payload: object) -> InvitationTargetDTO:
        fields = PostgresInvitationMapper._fields(payload)
        kind = InvitationTargetKind(fields.get("kind"))
        if kind is InvitationTargetKind.ORGANIZATION:
            PostgresInvitationMapper._fields(fields, {"kind", "organizationId"})
            return OrganizationGrantTargetDTO(
                organization_id=OrganizationId(
                    PostgresInvitationMapper._uuid(fields, "organizationId")
                )
            )
        if kind is InvitationTargetKind.PROJECT:
            PostgresInvitationMapper._fields(fields, {"kind", "projectId"})
            return ProjectGrantTargetDTO(
                project_id=ProjectId(PostgresInvitationMapper._uuid(fields, "projectId"))
            )
        if kind is InvitationTargetKind.ACCESS_GROUP:
            PostgresInvitationMapper._fields(fields, {"kind", "projectId", "accessGroupId"})
            return AccessGroupGrantTargetDTO(
                project_id=ProjectId(PostgresInvitationMapper._uuid(fields, "projectId")),
                access_group_id=AccessGroupId(
                    PostgresInvitationMapper._uuid(fields, "accessGroupId")
                ),
            )
        if kind is InvitationTargetKind.APPLICATION_ACCOUNT:
            PostgresInvitationMapper._fields(
                fields, {"kind", "projectId", "applicationPrincipalId"}
            )
            return ApplicationAccountGrantTargetDTO(
                project_id=ProjectId(PostgresInvitationMapper._uuid(fields, "projectId")),
                application_principal_id=PrincipalId(
                    PostgresInvitationMapper._uuid(fields, "applicationPrincipalId")
                ),
            )
        if kind is InvitationTargetKind.PIPELINE:
            PostgresInvitationMapper._fields(fields, {"kind", "pipelineId"})
            return InvitationPipelineTargetDTO(
                pipeline_id=PostgresInvitationMapper._uuid(fields, "pipelineId")
            )
        if kind is InvitationTargetKind.DEPLOYMENT:
            PostgresInvitationMapper._fields(fields, {"kind", "deploymentId"})
            return InvitationDeploymentTargetDTO(
                deployment_id=PostgresInvitationMapper._uuid(fields, "deploymentId")
            )
        if kind is InvitationTargetKind.COLLECTION:
            PostgresInvitationMapper._fields(fields, {"kind", "collectionId"})
            return InvitationCollectionTargetDTO(
                collection_id=PostgresInvitationMapper._uuid(fields, "collectionId")
            )
        if kind is InvitationTargetKind.SOURCE:
            PostgresInvitationMapper._fields(fields, {"kind", "sourceId"})
            return InvitationSourceTargetDTO(
                source_id=PostgresInvitationMapper._uuid(fields, "sourceId")
            )
        if kind is InvitationTargetKind.MODEL_CONNECTION:
            PostgresInvitationMapper._fields(fields, {"kind", "modelConnectionId"})
            return InvitationModelConnectionTargetDTO(
                model_connection_id=PostgresInvitationMapper._uuid(fields, "modelConnectionId")
            )
        if kind is InvitationTargetKind.PROCESSING_PROFILE:
            PostgresInvitationMapper._fields(fields, {"kind", "processingProfileId"})
            return InvitationProcessingProfileTargetDTO(
                processing_profile_id=PostgresInvitationMapper._uuid(fields, "processingProfileId")
            )
        PostgresInvitationMapper._fields(fields, {"kind", "embeddingProfileId"})
        return InvitationEmbeddingProfileTargetDTO(
            embedding_profile_id=PostgresInvitationMapper._uuid(fields, "embeddingProfileId")
        )

    @staticmethod
    def _target_payload(target: InvitationTargetDTO) -> dict[str, object]:
        if isinstance(target, OrganizationGrantTargetDTO):
            return {
                "kind": InvitationTargetKind.ORGANIZATION.value,
                "organizationId": str(target.organization_id.value),
            }
        if isinstance(target, ProjectGrantTargetDTO):
            return {
                "kind": InvitationTargetKind.PROJECT.value,
                "projectId": str(target.project_id.value),
            }
        if isinstance(target, AccessGroupGrantTargetDTO):
            return {
                "kind": InvitationTargetKind.ACCESS_GROUP.value,
                "projectId": str(target.project_id.value),
                "accessGroupId": str(target.access_group_id.value),
            }
        if isinstance(target, ApplicationAccountGrantTargetDTO):
            return {
                "kind": InvitationTargetKind.APPLICATION_ACCOUNT.value,
                "projectId": str(target.project_id.value),
                "applicationPrincipalId": str(target.application_principal_id.value),
            }
        if isinstance(target, InvitationPipelineTargetDTO):
            return {
                "kind": InvitationTargetKind.PIPELINE.value,
                "pipelineId": str(target.pipeline_id),
            }
        if isinstance(target, InvitationDeploymentTargetDTO):
            return {
                "kind": InvitationTargetKind.DEPLOYMENT.value,
                "deploymentId": str(target.deployment_id),
            }
        if isinstance(target, InvitationCollectionTargetDTO):
            return {
                "kind": InvitationTargetKind.COLLECTION.value,
                "collectionId": str(target.collection_id),
            }
        if isinstance(target, InvitationSourceTargetDTO):
            return {"kind": InvitationTargetKind.SOURCE.value, "sourceId": str(target.source_id)}
        if isinstance(target, InvitationModelConnectionTargetDTO):
            return {
                "kind": InvitationTargetKind.MODEL_CONNECTION.value,
                "modelConnectionId": str(target.model_connection_id),
            }
        if isinstance(target, InvitationProcessingProfileTargetDTO):
            return {
                "kind": InvitationTargetKind.PROCESSING_PROFILE.value,
                "processingProfileId": str(target.processing_profile_id),
            }
        return {
            "kind": InvitationTargetKind.EMBEDDING_PROFILE.value,
            "embeddingProfileId": str(target.embedding_profile_id),
        }
