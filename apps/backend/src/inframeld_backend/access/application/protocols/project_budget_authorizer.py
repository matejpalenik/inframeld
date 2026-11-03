from typing import Protocol

from inframeld_backend.access.application.dtos.project_action_authorization_dto import (
    ProjectActionAuthorizationDTO,
)
from inframeld_backend.access.application.dtos.project_action_authorization_request_dto import (
    ProjectActionAuthorizationRequestDTO,
)
from inframeld_backend.access.application.protocols.authorizer import Authorizer


class ProjectBudgetAuthorizer(
    Authorizer[ProjectActionAuthorizationRequestDTO, ProjectActionAuthorizationDTO],
    Protocol,
):
    """Check exact Project budget authority using current caller facts.

    The trusted workflow selects inspect-budget or manage-budget. Eligible
    humans and applications may inspect with that exact grant. Management
    additionally requires an active human, even if an application has a stored
    management grant. Other actions are outside this capability.

    Preserve current credential, recovery and visibility checks before returning
    the matched organization and Project. Facts cannot substitute another actor.
    The consuming operation checks returned scope before mutation or replay.
    This capability neither verifies credentials nor manages a transaction.
    """
