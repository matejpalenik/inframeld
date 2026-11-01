from typing import Protocol

from inframeld_backend.access.application.dtos.deletion_status_authorization_dto import (
    DeletionStatusAuthorizationDTO,
)
from inframeld_backend.access.application.dtos.deletion_status_authorization_request_dto import (
    DeletionStatusAuthorizationRequestDTO,
)
from inframeld_backend.access.application.protocols.authorizer import Authorizer


class DeletionStatusAuthorizer(
    Authorizer[DeletionStatusAuthorizationRequestDTO, DeletionStatusAuthorizationDTO], Protocol
):
    """Require a currently eligible human before matching retained initiator history.

    Project membership and current Delete authority are not prerequisites. The
    result grants no deletion, cancellation, continuation or restoration. The
    consuming reader must still match the exact original initiator and operation.
    """
