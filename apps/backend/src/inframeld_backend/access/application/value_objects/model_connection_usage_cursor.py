from base64 import b64decode, urlsafe_b64encode
from binascii import Error as Base64Error
from dataclasses import dataclass
from json import dumps, loads
from re import fullmatch
from typing import Self
from uuid import UUID

from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.indexing.domain.value_objects.embedding_profile_id import EmbeddingProfileId
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class ModelConnectionUsageCursor:
    """Bind a saved profile position to an installation, Project and connection."""

    installation_id: InstallationId
    project_id: ProjectId
    connection_id: ModelConnectionId
    after: EmbeddingProfileId

    @classmethod
    def from_token(cls, token: str) -> Self:
        try:
            if not 1 <= len(token) <= 1024 or fullmatch(r"[A-Za-z0-9_-]+", token) is None:
                raise ValueError("Invalid cursor encoding.")
            data: object = loads(
                b64decode(token + "=" * (-len(token) % 4), altchars=b"-_", validate=True).decode()
            )
            match data:
                case [
                    int() as version,
                    "model-connection-usage",
                    "id-asc",
                    str() as installation,
                    str() as project,
                    str() as connection,
                    str() as after,
                ] if type(version) is int and version == 1:
                    return cls(
                        InstallationId(UUID(installation)),
                        ProjectId(UUID(project)),
                        ModelConnectionId(UUID(connection)),
                        EmbeddingProfileId(UUID(after)),
                    )
                case _:
                    raise ValueError("Incompatible cursor contents.")
        except (ValueError, Base64Error, UnicodeError, RecursionError) as error:
            raise ValueError(
                "The model connection usage cursor is invalid or incompatible."
            ) from error

    def to_token(self) -> str:
        payload = dumps(
            [
                1,
                "model-connection-usage",
                "id-asc",
                str(self.installation_id.value),
                str(self.project_id.value),
                str(self.connection_id.value),
                str(self.after.value),
            ],
            separators=(",", ":"),
        )
        return urlsafe_b64encode(payload.encode()).decode().rstrip("=")
