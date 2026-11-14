from typing import Literal

from pydantic import BaseModel, Field


class DoclingProcessingDefinitionResponse(BaseModel):
    docling_slim_version: str = Field(serialization_alias="doclingSlimVersion")
    docling_core_version: str = Field(serialization_alias="doclingCoreVersion")
    asset_manifest_sha256: str = Field(serialization_alias="assetManifestSha256")
    max_content_tokens: int = Field(serialization_alias="maxContentTokens", ge=1, le=1024)
    merge_peers: bool = Field(serialization_alias="mergePeers")
    repeat_table_header: bool = Field(serialization_alias="repeatTableHeader")
    ocr_enabled: Literal[False] = Field(serialization_alias="ocrEnabled")
