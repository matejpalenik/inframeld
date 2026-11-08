from typing import Annotated

from pydantic import Field, RootModel

from inframeld_backend.access.http.responses.application_key_first_delivery_response import (
    ApplicationKeyFirstDeliveryResponse,
)
from inframeld_backend.access.http.responses.application_key_issuance_replay_response import (
    ApplicationKeyIssuanceReplayResponse,
)


class ApplicationKeyIssueResponse(
    RootModel[
        Annotated[
            ApplicationKeyFirstDeliveryResponse | ApplicationKeyIssuanceReplayResponse,
            Field(discriminator="secret_available"),
        ]
    ]
):
    """Distinguish first credential delivery from credential-free original recovery."""
