from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.json_schema import SkipJsonSchema

from inframeld_backend.access.http.requests.invitation_action_grant_request import (
    InvitationActionGrantRequest,
)
from inframeld_backend.access.http.requests.invitation_admission_only_request import (
    InvitationAdmissionOnlyRequest,
)
from inframeld_backend.access.http.requests.invitation_project_access_revision_request import (
    InvitationProjectAccessRevisionRequest,
)
from inframeld_backend.access.http.types.invitation_assignment_request import (
    InvitationAssignmentRequest,
)
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class InvitationIssueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    organization_id: UUID = Field(alias="organizationId")
    assignments: list[InvitationAssignmentRequest] = Field(min_length=1, max_length=100)
    expected_access_revision: int = Field(
        alias="expectedAccessRevision",
        strict=True,
        ge=0,
        le=RevisionValidation.MAX_VALUE,
        json_schema_extra={"format": "int64"},
    )
    expected_project_access_revisions: list[InvitationProjectAccessRevisionRequest] = Field(
        alias="expectedProjectAccessRevisions", max_length=100
    )
    expires_in_seconds: (
        Annotated[int, Field(strict=True, gt=0, le=2592000)] | SkipJsonSchema[None]
    ) = Field(default=None, alias="expiresInSeconds")

    @model_validator(mode="after")
    def _require_unambiguous_intent(self) -> Self:
        if "expires_in_seconds" in self.model_fields_set and self.expires_in_seconds is None:
            raise ValueError("A submitted invitation lifetime cannot be null.")
        projects = [item.project_id for item in self.expected_project_access_revisions]
        if len(projects) != len(set(projects)):
            raise ValueError("Review each affected Project exactly once.")
        seen: set[tuple[str, ...]] = set()
        for item in self.assignments:
            if isinstance(item, InvitationAdmissionOnlyRequest) and len(self.assignments) != 1:
                raise ValueError("Admission-only intent must stand alone.")
            identity = (
                (item.kind, item.target.model_dump_json(by_alias=True), item.action_id)
                if isinstance(item, InvitationActionGrantRequest)
                else (item.model_dump_json(by_alias=True),)
            )
            if identity in seen:
                raise ValueError("Each exact assignment must appear once.")
            seen.add(identity)
        return self
