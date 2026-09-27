"""Define the stable HTTP representation of the current local human session."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue


def _preserve_public_schema(schema: dict[str, JsonValue]) -> None:
    """Keep internal component documentation out of the existing public schema."""
    schema.pop("description", None)


class CurrentSessionResponse(BaseModel):
    """Expose the admitted local principal UUID as principalId, without provider credentials."""

    model_config = ConfigDict(json_schema_extra=_preserve_public_schema)

    principal_id: UUID = Field(serialization_alias="principalId")
