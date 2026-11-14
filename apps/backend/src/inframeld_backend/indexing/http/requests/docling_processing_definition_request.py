from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DoclingProcessingDefinitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True, strict=True)

    docling_slim_version: str = Field(alias="doclingSlimVersion", min_length=1, max_length=32)
    docling_core_version: str = Field(alias="doclingCoreVersion", min_length=1, max_length=32)
    asset_manifest_sha256: str = Field(alias="assetManifestSha256", pattern="^[a-f0-9]{64}$")
    max_content_tokens: int = Field(alias="maxContentTokens", ge=1, le=1024)
    merge_peers: bool = Field(alias="mergePeers")
    repeat_table_header: bool = Field(alias="repeatTableHeader")
    ocr_enabled: Literal[False] = Field(alias="ocrEnabled")

    @field_validator("ocr_enabled", mode="before")
    @classmethod
    def _requires_disabled_ocr(cls, value: object) -> object:
        if value is not False:
            raise ValueError("OCR must be disabled for this processing definition.")
        return value
