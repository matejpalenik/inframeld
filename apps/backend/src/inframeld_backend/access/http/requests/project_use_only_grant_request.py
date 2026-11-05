"""Parse the supported use-only project grant command."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class ProjectUseOnlyGrantRequest(BaseModel):
    recipient_principal_id: UUID = Field(alias="recipientPrincipalId")
    action_id: Literal[ProjectAction.CREATE_ACCESS_GROUPS] = Field(alias="actionId")
    expected_access_revision: int = Field(
        alias="expectedAccessRevision",
        strict=True,
        ge=0,
        le=RevisionValidation.MAX_VALUE,
        json_schema_extra={"format": "int64"},
    )
