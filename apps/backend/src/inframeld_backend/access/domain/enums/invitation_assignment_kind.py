from enum import StrEnum


class InvitationAssignmentKind(StrEnum):
    PROJECT_MEMBERSHIP = "project-membership"
    GROUP_MEMBERSHIP = "group-membership"
    GROUP_MANAGER = "group-manager"
    ACTION_GRANT = "action-grant"
    ADMISSION_ONLY = "admission-only"
