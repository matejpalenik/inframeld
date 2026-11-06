from uuid import UUID

from pydantic import BaseModel, Field

from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind


class AccessGroupPrincipalResponse(BaseModel):
    principal_id: UUID = Field(serialization_alias="principalId")
    kind: PrincipalKind
    display_name: str = Field(serialization_alias="displayName")
