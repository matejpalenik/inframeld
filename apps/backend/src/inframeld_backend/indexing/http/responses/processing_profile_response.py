from uuid import UUID

from pydantic import BaseModel, Field

from inframeld_backend.indexing.http.responses.docling_processing_definition_response import (
    DoclingProcessingDefinitionResponse,
)


class ProcessingProfileResponse(BaseModel):
    project_id: UUID = Field(serialization_alias="projectId")
    processing_profile_id: UUID = Field(serialization_alias="processingProfileId")
    name: str
    display_name: str = Field(serialization_alias="displayName")
    definition: DoclingProcessingDefinitionResponse
