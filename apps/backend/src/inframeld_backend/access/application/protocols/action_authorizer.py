from typing import Protocol

from inframeld_backend.access.application.dtos.project_action_authorization_dto import (
    ProjectActionAuthorizationDTO,
)
from inframeld_backend.access.application.dtos.project_action_authorization_request_dto import (
    ProjectActionAuthorizationRequestDTO,
)
from inframeld_backend.access.application.protocols.authorizer import Authorizer


class ActionAuthorizer(
    Authorizer[ProjectActionAuthorizationRequestDTO, ProjectActionAuthorizationDTO],
    Protocol,
):
    """Check permission to perform one named action in one project.

    For example, Alice creating access groups in Support needs that exact
    action's use permission. Project membership alone does not permit the action.
    Check her current account status, recovery block, membership and action grant.

    The inherited `require_authorization()` accepts the project's ID and the
    action selected by the trusted workflow. Return the matched organization
    and exact project. The caller checks that project against its requested
    target before using the scope for further work.

    Report an unavailable or hidden project with `ResourceNotFoundError` before
    checking action permission. On a visible project, failed eligibility or a
    missing use grant raises `AccessDeniedError`. Performing an action does not
    establish permission to grant it to someone else.
    """
