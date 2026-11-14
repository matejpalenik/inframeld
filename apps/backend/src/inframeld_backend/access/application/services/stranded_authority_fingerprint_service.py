import json

from inframeld_backend.access.application.commands.repair_stranded_authority_command import (
    RepairStrandedAuthorityCommand,
)
from inframeld_backend.access.application.dtos.access_group_grant_target_dto import (
    AccessGroupGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.action_grantor_repair_responsibility_dto import (
    ActionGrantorRepairResponsibilityDTO,
)
from inframeld_backend.access.application.dtos.group_manager_repair_responsibility_dto import (
    GroupManagerRepairResponsibilityDTO,
)
from inframeld_backend.access.application.dtos.model_connection_grant_target_dto import (
    ModelConnectionGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.organization_grant_target_dto import (
    OrganizationGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.project_grant_target_dto import ProjectGrantTargetDTO
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)


class StrandedAuthorityFingerprintService:
    def __init__(self, request_fingerprint_service: RequestFingerprintService) -> None:
        self._request_fingerprint_service = request_fingerprint_service

    def for_repair(
        self, command: RepairStrandedAuthorityCommand, identity: VerifiedHumanIdentityDTO
    ) -> RequestFingerprint:
        responsibility = command.responsibility
        legacy = (
            isinstance(responsibility, ActionGrantorRepairResponsibilityDTO)
            and isinstance(responsibility.target, ProjectGrantTargetDTO)
            and responsibility.action_id.value == ProjectAction.EDIT_PROJECT_METADATA.value
        )
        meaning: str | list[str]
        if (
            legacy
            and isinstance(responsibility, ActionGrantorRepairResponsibilityDTO)
            and isinstance(responsibility.target, ProjectGrantTargetDTO)
        ):
            meaning = str(responsibility.target.project_id.value)
        else:
            meaning = self._meaning(responsibility)
        return self._request_fingerprint_service.fingerprint(
            purpose="project-metadata-repair" if legacy else "stranded-authority-repair",
            canonical_request=json.dumps(
                [
                    "repair-stranded-authority",
                    str(command.expected_installation_id.value),
                    identity.authority.value,
                    identity.subject.value,
                    str(command.expected_identity_id),
                    meaning,
                    command.expected_access_revision,
                    command.operator_label,
                    command.reason,
                ],
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8"),
        )

    @staticmethod
    def _meaning(
        responsibility: GroupManagerRepairResponsibilityDTO | ActionGrantorRepairResponsibilityDTO,
    ) -> list[str]:
        if isinstance(responsibility, GroupManagerRepairResponsibilityDTO):
            return [
                responsibility.kind.value,
                str(responsibility.project_id.value),
                str(responsibility.access_group_id.value),
            ]
        target = responsibility.target
        if isinstance(target, OrganizationGrantTargetDTO):
            scope = ["organization", str(target.organization_id.value)]
        elif isinstance(target, ProjectGrantTargetDTO):
            scope = ["project", str(target.project_id.value)]
        elif isinstance(target, AccessGroupGrantTargetDTO):
            scope = [
                "access-group",
                str(target.project_id.value),
                str(target.access_group_id.value),
            ]
        elif isinstance(target, ModelConnectionGrantTargetDTO):
            scope = [
                "model-connection",
                str(target.project_id.value),
                str(target.model_connection_id.value),
            ]
        else:
            scope = [
                "application-account",
                str(target.project_id.value),
                str(target.application_principal_id.value),
            ]
        return [responsibility.kind.value, *scope, responsibility.action_id.value]
