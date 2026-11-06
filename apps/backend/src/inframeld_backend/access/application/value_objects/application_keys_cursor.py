import base64
import binascii
import json
import re
from dataclasses import dataclass
from typing import Self
from uuid import UUID

from inframeld_backend.access.domain.value_objects.application_key_id import ApplicationKeyId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class ApplicationKeysCursor:
    """Identify an endpoint-scoped UUID position without carrying authority or secrets."""

    installation_id: InstallationId
    organization_id: OrganizationId
    project_id: ProjectId
    application_principal_id: PrincipalId
    after: ApplicationKeyId

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
                    "application-keys",
                    "key-id-asc",
                    str() as installation,
                    str() as organization,
                    str() as project,
                    str() as application,
                    str() as after,
                ] if type(version) is int and version == 1:
                    return cls(
                        InstallationId(UUID(installation)),
                        OrganizationId(UUID(organization)),
                        ProjectId(UUID(project)),
                        PrincipalId(UUID(application)),
                        ApplicationKeyId(UUID(after)),
                    )
                case _:
                    raise ValueError("Incompatible cursor contents.")
        except (ValueError, binascii.Error, UnicodeError, RecursionError) as error:
            raise ValueError("The application keys cursor is invalid or incompatible.") from error

    def to_token(self) -> str:
        parts = [
            1,
            "application-keys",
            "key-id-asc",
            str(self.installation_id.value),
            str(self.organization_id.value),
            str(self.project_id.value),
            str(self.application_principal_id.value),
            str(self.after.value),
        ]
        return (
            base64.urlsafe_b64encode(json.dumps(parts, separators=(",", ":")).encode())
            .decode()
            .rstrip("=")
        )
