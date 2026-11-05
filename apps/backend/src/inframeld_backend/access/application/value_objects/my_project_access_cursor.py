import base64
import binascii
import json
import re
from dataclasses import dataclass
from typing import Literal, Self
from uuid import UUID

from inframeld_backend.access.application.value_objects.my_project_access_position import (
    MyProjectAccessPosition,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class MyProjectAccessCursor:
    installation_id: InstallationId
    organization_id: OrganizationId
    project_id: ProjectId
    principal_id: PrincipalId
    after: MyProjectAccessPosition

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
                    "my-project-access",
                    "combined-v1",
                    str() as installation,
                    str() as organization,
                    str() as project,
                    str() as principal,
                    str() as target,
                    str() as kind,
                    (str() | None) as action,
                ] if type(version) is int and version == 1:
                    relationship: Literal["grant", "membership", "management"]
                    if kind == "grant":
                        relationship = "grant"
                    elif kind == "membership":
                        relationship = "membership"
                    elif kind == "management":
                        relationship = "management"
                    else:
                        raise ValueError("Unsupported own-access relationship kind.")
                    return cls(
                        InstallationId(UUID(installation)),
                        OrganizationId(UUID(organization)),
                        ProjectId(UUID(project)),
                        PrincipalId(UUID(principal)),
                        MyProjectAccessPosition(
                            relationship,
                            UUID(target),
                            ActionId(action) if action is not None else None,
                        ),
                    )
                case _:
                    raise ValueError("Incompatible cursor contents.")
        except (ValueError, binascii.Error, UnicodeError, RecursionError) as error:
            raise ValueError("The own-access cursor is invalid or incompatible.") from error

    def to_token(self) -> str:
        parts = [
            1,
            "my-project-access",
            "combined-v1",
            str(self.installation_id.value),
            str(self.organization_id.value),
            str(self.project_id.value),
            str(self.principal_id.value),
            str(self.after.target_id),
            self.after.kind,
            self.after.action_id.value if self.after.action_id is not None else None,
        ]
        return (
            base64.urlsafe_b64encode(json.dumps(parts, separators=(",", ":")).encode())
            .decode()
            .rstrip("=")
        )
