import base64
import binascii
import json
import re
from dataclasses import dataclass
from typing import Self
from uuid import UUID

from inframeld_backend.access.application.dtos.access_group_grant_target_dto import (
    AccessGroupGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.application_account_grant_target_dto import (
    ApplicationAccountGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.model_connection_grant_target_dto import (
    ModelConnectionGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.project_grant_target_dto import (
    ProjectGrantTargetDTO,
)
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class GrantRecipientsCursor:
    """Bind one concrete Access target and action to a recipient UUID position."""

    installation_id: InstallationId
    organization_id: OrganizationId
    target: (
        ProjectGrantTargetDTO
        | AccessGroupGrantTargetDTO
        | ApplicationAccountGrantTargetDTO
        | ModelConnectionGrantTargetDTO
    )
    action_id: ActionId
    after: PrincipalId

    @classmethod
    def from_token(cls, token: str) -> Self:
        try:
            if not 1 <= len(token) <= 1024 or re.fullmatch(r"[A-Za-z0-9_-]+", token) is None:
                raise ValueError("Invalid cursor encoding.")
            decoded = base64.b64decode(
                token + "=" * (-len(token) % 4), altchars=b"-_", validate=True
            )
            parts: object = json.loads(decoded.decode("utf-8"))
            match parts:
                case [
                    int() as version,
                    "grant-recipients",
                    "recipient-id-asc",
                    str() as installed,
                    str() as organization,
                    str() as kind,
                    (str() | None) as project,
                    str() as target,
                    str() as action,
                    str() as after,
                ] if type(version) is int and version == 1:
                    match kind, project:
                        case "project", str() as project_id:
                            if UUID(project_id) != UUID(target):
                                raise ValueError("The Project target binding changed.")
                            selected = ProjectGrantTargetDTO(project_id=ProjectId(UUID(target)))
                        case "access-group", str() as project_id:
                            selected = AccessGroupGrantTargetDTO(
                                project_id=ProjectId(UUID(project_id)),
                                access_group_id=AccessGroupId(UUID(target)),
                            )
                        case "application-account", str() as project_id:
                            selected = ApplicationAccountGrantTargetDTO(
                                project_id=ProjectId(UUID(project_id)),
                                application_principal_id=PrincipalId(UUID(target)),
                            )
                        case "model-connection", str() as project_id:
                            selected = ModelConnectionGrantTargetDTO(
                                project_id=ProjectId(UUID(project_id)),
                                model_connection_id=ModelConnectionId(UUID(target)),
                            )
                        case _:
                            raise ValueError("Incompatible target binding.")
                    return cls(
                        installation_id=InstallationId(UUID(installed)),
                        organization_id=OrganizationId(UUID(organization)),
                        target=selected,
                        action_id=ActionId(action),
                        after=PrincipalId(UUID(after)),
                    )
                case _:
                    raise ValueError("Incompatible cursor contents.")
        except (ValueError, binascii.Error, UnicodeError, RecursionError) as error:
            raise ValueError("The grant recipients cursor is invalid or incompatible.") from error

    def to_token(self) -> str:
        match self.target:
            case ProjectGrantTargetDTO() as target:
                kind, project, identity = (
                    "project",
                    str(target.project_id.value),
                    target.project_id.value,
                )
            case AccessGroupGrantTargetDTO() as target:
                kind, project, identity = (
                    "access-group",
                    str(target.project_id.value),
                    target.access_group_id.value,
                )
            case ApplicationAccountGrantTargetDTO() as target:
                kind, project, identity = (
                    "application-account",
                    str(target.project_id.value),
                    target.application_principal_id.value,
                )
            case ModelConnectionGrantTargetDTO() as target:
                kind, project, identity = (
                    "model-connection",
                    str(target.project_id.value),
                    target.model_connection_id.value,
                )
        parts = [
            1,
            "grant-recipients",
            "recipient-id-asc",
            str(self.installation_id.value),
            str(self.organization_id.value),
            kind,
            project,
            str(identity),
            self.action_id.value,
            str(self.after.value),
        ]
        return (
            base64.urlsafe_b64encode(json.dumps(parts, separators=(",", ":")).encode())
            .decode()
            .rstrip("=")
        )
