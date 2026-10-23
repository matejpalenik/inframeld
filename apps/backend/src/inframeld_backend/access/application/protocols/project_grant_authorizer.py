from typing import Protocol

from inframeld_backend.access.application.dtos.project_grant_authorization_dto import (
    ProjectGrantAuthorizationDTO,
)
from inframeld_backend.access.application.dtos.project_use_only_grant_authorization_request_dto import (
    ProjectUseOnlyGrantAuthorizationRequestDTO,
)
from inframeld_backend.access.application.protocols.authorizer import Authorizer


class ProjectGrantAuthorizer(
    Authorizer[ProjectUseOnlyGrantAuthorizationRequestDTO, ProjectGrantAuthorizationDTO],
    Protocol,
):
    """Check whether a caller may give a human use-only permission in a project.

    For example, Alice granting Bob `create-access-groups` on Support needs
    delegation authority for that action and project, independently of her own
    use permission. Alice must be an active human project member with no pending
    recovery. Bob must be an active human in the same organization and a member
    of the project. Use-only lets Bob perform the action, not delegate it.

    The inherited `require_authorization()` accepts the project, recipient and
    action being delegated. Return the exact project, its organization and its
    current permission revision. The caller checks the project match before
    using this scope for reservation, replay or persistence.

    Hide unavailable projects with `ResourceNotFoundError`. Check Alice's current
    eligibility and delegation authority before revealing whether Bob exists.
    After that check, a missing Bob raises `ResourceNotFoundError`. Failed caller
    authority or recipient eligibility raises `AccessDeniedError`.
    """
