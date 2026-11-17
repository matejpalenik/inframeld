from base64 import b64decode, urlsafe_b64encode
from binascii import Error as Base64Error
from dataclasses import dataclass
from json import dumps, loads
from re import fullmatch
from typing import Self
from uuid import UUID

from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.indexing.domain.value_objects.embedding_profile_id import (
    EmbeddingProfileId,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class EmbeddingProfilesCursor:
    """Bind the UUID position to this installation, Project and list operation."""

    installation_id: InstallationId
    project_id: ProjectId
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
                    "embedding-profiles:id-asc:v1",
                    str() as installation,
                    str() as project,
                    str() as after,
                ]:
                    return cls(
                        InstallationId(UUID(installation)),
                        ProjectId(UUID(project)),
                        EmbeddingProfileId(UUID(after)),
                    )
                case _:
                    raise ValueError("Incompatible cursor contents.")
        except (ValueError, Base64Error, UnicodeError, RecursionError) as error:
            raise ValueError("The Embedding Profile cursor is invalid or incompatible.") from error

    def to_token(self) -> str:
        data = [
            "embedding-profiles:id-asc:v1",
            str(self.installation_id.value),
            str(self.project_id.value),
            str(self.after.value),
        ]
        return urlsafe_b64encode(dumps(data, separators=(",", ":")).encode()).decode().rstrip("=")
