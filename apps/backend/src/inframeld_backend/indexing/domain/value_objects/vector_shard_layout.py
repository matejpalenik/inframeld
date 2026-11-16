from base64 import b32encode
from dataclasses import dataclass
from hashlib import sha256
from typing import Literal

from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.indexing.domain.value_objects.embedding_profile_id import EmbeddingProfileId
from inframeld_backend.indexing.domain.value_objects.vector_layout_id import VectorLayoutId


@dataclass(frozen=True, slots=True, kw_only=True)
class VectorShardLayout:
    """Fix physical shard identities and record placement for one scoped profile."""

    organization_id: OrganizationId
    project_id: ProjectId
    embedding_profile_id: EmbeddingProfileId
    layout_id: VectorLayoutId
    shard_count: int
    version: Literal[1] = 1

    def __post_init__(self) -> None:
        if (
            type(self.organization_id) is not OrganizationId
            or type(self.project_id) is not ProjectId
            or type(self.embedding_profile_id) is not EmbeddingProfileId
            or type(self.layout_id) is not VectorLayoutId
        ):
            raise TypeError("A vector shard layout requires typed scope and layout IDs.")

        if type(self.version) is not int:
            raise TypeError("The placement version must be a whole number.")
        if self.version != 1:
            raise ValueError("Only placement version 1 is supported.")

        if type(self.shard_count) is not int:
            raise TypeError("The shard count must be a whole number.")
        if not 1 <= self.shard_count <= 2:
            raise ValueError("The shard count must be one or two.")

    def collection_name(self, shard_ordinal: int) -> str:
        """Derive the exact physical collection name for a zero-based shard."""
        if type(shard_ordinal) is not int:
            raise TypeError("The shard ordinal must be a whole number.")
        if not 0 <= shard_ordinal < self.shard_count:
            raise ValueError("The shard ordinal is outside the saved layout.")

        identity = (
            self.organization_id.value.bytes
            + self.project_id.value.bytes
            + self.embedding_profile_id.value.bytes
            + self.layout_id.value.bytes
            + bytes((shard_ordinal,))
        )
        digest = b32encode(sha256(identity).digest()).decode("ascii").rstrip("=").lower()
        return f"im-v1-{digest}"

    def shard_for(self, record_id: bytes) -> int:
        """Route the exact stable record ID using the saved shard count."""
        if type(record_id) is not bytes:
            raise TypeError("A stable record ID requires bytes.")

        return int.from_bytes(sha256(record_id).digest(), "big") % self.shard_count
