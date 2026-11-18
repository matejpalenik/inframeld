from dataclasses import dataclass, field
from uuid import UUID

from inframeld_backend.shared.application.value_objects.artifact_content_digest import (
    ArtifactContentDigest,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class ParsedPdfDTO:
    """Carry verified parser output before the owning worker authorizes publication."""

    attempt_id: UUID
    source_digest: ArtifactContentDigest
    canonical_digest: ArtifactContentDigest
    canonical_bytes: bytes = field(repr=False)
    chunk_ranges: tuple[tuple[int, int], ...]
