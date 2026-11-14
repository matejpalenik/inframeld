from uuid import UUID

from pydantic import TypeAdapter

from inframeld_backend.access.application.commands.repair_stranded_authority_command import (
    RepairStrandedAuthorityCommand,
)
from inframeld_backend.access.application.dtos.access_group_grant_target_dto import (
    AccessGroupGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.action_grantor_repair_responsibility_dto import (
    ActionGrantorRepairResponsibilityDTO,
)
from inframeld_backend.access.application.dtos.application_account_grant_target_dto import (
    ApplicationAccountGrantTargetDTO,
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
from inframeld_backend.access.application.dtos.stranded_authority_repair_result_dto import (
    StrandedAuthorityRepairResultDTO,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.cli.errors.stranded_authority_maintenance_input_error import (
    StrandedAuthorityMaintenanceInputError,
)
from inframeld_backend.access.cli.mappers.maintenance_input_mapper import MaintenanceInputMapper
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("A string is required.")
    return value


class StrandedAuthorityMaintenanceMapper:
    @staticmethod
    def read(payload: bytes) -> RepairStrandedAuthorityCommand:
        operation_id = None
        try:
            values = MaintenanceInputMapper.read(payload)
            operation_id = MaintenanceInputMapper.correlation(values)
            if set(values) != {
                "schemaVersion",
                "mode",
                "expectedInstallationId",
                "operationId",
                "operatorLabel",
                "reason",
                "expectedAccessRevision",
                "expectedIdentityId",
                "identityProof",
                "responsibility",
            }:
                raise ValueError("Invalid maintenance fields.")
            if (
                type(values["schemaVersion"]) is not int
                or values["schemaVersion"] != 1
                or values["mode"] != "repair-stranded-authority"
            ):
                raise ValueError("Unsupported maintenance request.")
            proof = TypeAdapter(dict[str, object]).validate_python(
                values["identityProof"], strict=True
            )
            if set(proof) != {"kind", "accessToken"} or proof["kind"] != "hydra-access-token":
                raise ValueError("Unsupported recipient proof.")
            revision = values["expectedAccessRevision"]
            if type(revision) is not int:
                raise ValueError("A whole-number review revision is required.")
            return RepairStrandedAuthorityCommand(
                expected_installation_id=InstallationId(
                    UUID(_text(values["expectedInstallationId"]))
                ),
                operation_id=OperationId(_text(values["operationId"])),
                responsibility=StrandedAuthorityMaintenanceMapper._responsibility(
                    values["responsibility"]
                ),
                expected_access_revision=revision,
                expected_identity_id=UUID(_text(values["expectedIdentityId"])),
                operator_label=_text(values["operatorLabel"]),
                reason=_text(values["reason"]),
                identity_proof=HumanAccessTokenCredential(_text(proof["accessToken"])),
            )
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise StrandedAuthorityMaintenanceInputError(operation_id) from None

    @staticmethod
    def _responsibility(
        value: object,
    ) -> GroupManagerRepairResponsibilityDTO | ActionGrantorRepairResponsibilityDTO:
        values = TypeAdapter(dict[str, object]).validate_python(value, strict=True)
        if values.get("kind") == "group-manager":
            if set(values) != {"kind", "projectId", "accessGroupId"}:
                raise ValueError("Invalid group-manager responsibility.")
            return GroupManagerRepairResponsibilityDTO(
                ProjectId(UUID(_text(values["projectId"]))),
                AccessGroupId(UUID(_text(values["accessGroupId"]))),
            )
        if set(values) != {"kind", "target", "actionId"} or values["kind"] != "action-grantor":
            raise ValueError("Unsupported responsibility.")
        target = TypeAdapter(dict[str, object]).validate_python(values["target"], strict=True)
        kind = target.get("kind")
        if kind == "organization" and set(target) == {"kind", "organizationId"}:
            exact = OrganizationGrantTargetDTO(
                OrganizationId(UUID(_text(target["organizationId"])))
            )
        elif kind == "project" and set(target) == {"kind", "projectId"}:
            exact = ProjectGrantTargetDTO(ProjectId(UUID(_text(target["projectId"]))))
        elif kind == "access-group" and set(target) == {"kind", "projectId", "accessGroupId"}:
            exact = AccessGroupGrantTargetDTO(
                ProjectId(UUID(_text(target["projectId"]))),
                AccessGroupId(UUID(_text(target["accessGroupId"]))),
            )
        elif kind == "application-account" and set(target) == {
            "kind",
            "projectId",
            "applicationPrincipalId",
        }:
            exact = ApplicationAccountGrantTargetDTO(
                ProjectId(UUID(_text(target["projectId"]))),
                PrincipalId(UUID(_text(target["applicationPrincipalId"]))),
            )
        elif kind == "model-connection" and set(target) == {
            "kind",
            "projectId",
            "modelConnectionId",
        }:
            exact = ModelConnectionGrantTargetDTO(
                ProjectId(UUID(_text(target["projectId"]))),
                ModelConnectionId(UUID(_text(target["modelConnectionId"]))),
            )
        else:
            raise ValueError("Unsupported exact repair target.")
        return ActionGrantorRepairResponsibilityDTO(exact, ActionId(_text(values["actionId"])))

    @staticmethod
    def result(result: StrandedAuthorityRepairResultDTO) -> dict[str, object]:
        responsibility = result.responsibility
        rendered: dict[str, object]
        if isinstance(responsibility, GroupManagerRepairResponsibilityDTO):
            rendered = {
                "kind": responsibility.kind.value,
                "projectId": str(responsibility.project_id.value),
                "accessGroupId": str(responsibility.access_group_id.value),
            }
        else:
            target = responsibility.target
            if isinstance(target, OrganizationGrantTargetDTO):
                scope = {
                    "kind": "organization",
                    "organizationId": str(target.organization_id.value),
                }
            elif isinstance(target, ProjectGrantTargetDTO):
                scope = {"kind": "project", "projectId": str(target.project_id.value)}
            elif isinstance(target, AccessGroupGrantTargetDTO):
                scope = {
                    "kind": "access-group",
                    "projectId": str(target.project_id.value),
                    "accessGroupId": str(target.access_group_id.value),
                }
            elif isinstance(target, ModelConnectionGrantTargetDTO):
                scope = {
                    "kind": "model-connection",
                    "projectId": str(target.project_id.value),
                    "modelConnectionId": str(target.model_connection_id.value),
                }
            else:
                scope = {
                    "kind": "application-account",
                    "projectId": str(target.project_id.value),
                    "applicationPrincipalId": str(target.application_principal_id.value),
                }
            rendered = {
                "kind": responsibility.kind.value,
                "target": scope,
                "actionId": responsibility.action_id.value,
            }
        return {
            "schemaVersion": 1,
            "mode": "repair-stranded-authority",
            "operationId": result.operation_id.value,
            "installationId": str(result.installation_id.value),
            "principalId": str(result.recipient_id.value),
            "accessRevision": result.access_revision,
            "outcome": "repaired",
            "responsibility": rendered,
        }
