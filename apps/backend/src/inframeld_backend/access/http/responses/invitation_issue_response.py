from typing import Annotated

from pydantic import Field, RootModel

from inframeld_backend.access.http.responses.invitation_first_delivery_response import (
    InvitationFirstDeliveryResponse,
)
from inframeld_backend.access.http.responses.invitation_issuance_replay_response import (
    InvitationIssuanceReplayResponse,
)


class InvitationIssueResponse(
    RootModel[
        Annotated[
            InvitationFirstDeliveryResponse | InvitationIssuanceReplayResponse,
            Field(discriminator="secret_available"),
        ]
    ]
):
    """Deliver a secret once or retain only the original safe issuance metadata."""
