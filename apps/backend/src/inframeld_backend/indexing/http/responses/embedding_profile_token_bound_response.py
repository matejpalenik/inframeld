from pydantic import BaseModel

from inframeld_backend.shared.application.enums.model_token_bound_kind import ModelTokenBoundKind


class EmbeddingProfileTokenBoundResponse(BaseModel):
    kind: ModelTokenBoundKind
    implementation: str
    revision: str
