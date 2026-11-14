from dataclasses import dataclass
from typing import Literal

_PINNED_SOURCE = (
    "2.148.0",  # Docling Slim
    "2.106.0",  # Docling Core
    "7ea9f3c967a7bc66d2501e466334e7aef46a639e01a11376888321e0f0a51d0e",
)


@dataclass(frozen=True, slots=True, kw_only=True)
class DoclingProcessingDefinition:
    """Freeze effective chunking settings and source identities for offline Docling.

    The token budget counts content without tokenizer special tokens. Runtime
    availability and asset verification belong to the parser installation.
    """

    docling_slim_version: str
    docling_core_version: str
    asset_manifest_sha256: str
    max_content_tokens: int
    merge_peers: bool
    repeat_table_header: bool
    ocr_enabled: Literal[False]

    def __post_init__(self) -> None:
        source = (
            self.docling_slim_version,
            self.docling_core_version,
            self.asset_manifest_sha256,
        )
        if source != _PINNED_SOURCE:
            raise ValueError("Processing requires the pinned Docling versions and asset manifest.")

        if type(self.max_content_tokens) is not int:
            raise TypeError("The content token limit must be a whole number.")
        if not 1 <= self.max_content_tokens <= 1024:
            raise ValueError("A chunk must allow 1 to 1024 content tokens.")

        if type(self.merge_peers) is not bool or type(self.repeat_table_header) is not bool:
            raise TypeError("Merge peers and repeat table header must be booleans.")
        if self.ocr_enabled is not False:
            raise ValueError("OCR must be disabled for this processing definition.")
