from typing import Literal

from pydantic import BaseModel, Field

from inframeld_backend.access.http.responses.project_grant_target_response import (
    ProjectGrantTargetResponse,
)


class InitialProjectGrantResponse(BaseModel):
    target: ProjectGrantTargetResponse
    action_id: Literal[
        "manage-project-members",
        "create-access-groups",
        "create-application-accounts",
        "create-pipelines",
        "create-deployments",
        "manage-upload-defaults",
        "delete-project",
        "inspect-budget",
        "manage-budget",
        "manage-trace-policy",
        "delete-trace-history",
        "inspect-feedback",
        "create-collections",
        "create-sources",
        "create-model-connections",
        "create-processing-profiles",
        "create-embedding-profiles",
        "edit-project-metadata",
    ] = Field(serialization_alias="actionId")
    can_grant: Literal[True] = Field(serialization_alias="canGrant")
