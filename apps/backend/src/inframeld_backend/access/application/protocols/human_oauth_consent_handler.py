from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.decide_human_oauth_consent_command import (
    DecideHumanOAuthConsentCommand,
)
from inframeld_backend.access.application.dtos.human_oauth_consent_details_dto import (
    HumanOAuthConsentDetailsDTO,
)
from inframeld_backend.access.application.dtos.oauth_consent_continuation_dto import (
    OAuthConsentContinuationDTO,
)
from inframeld_backend.access.application.queries.inspect_human_oauth_consent_query import (
    InspectHumanOAuthConsentQuery,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)


class HumanOAuthConsentHandler(Protocol):
    """Let Alice inspect and decide whether this installation's CLI may act as her.

    Each call first rejects unsupported client/access requests. Supported requests
    then verify her current Kratos session, matching Hydra subject and recovery
    state. Local account admission is separate.
    Invalid sessions raise AuthenticationRequiredError, policy failures raise
    AccessDeniedError and unavailable dependencies raise DependencyUnavailableError.
    These checks do not fence a later provider call against concurrent recovery.
    """

    @abstractmethod
    async def inspect(
        self, *, credential: BrowserSessionCredential, query: InspectHumanOAuthConsentQuery
    ) -> HumanOAuthConsentDetailsDTO:
        """Return checked display data without approving or reserving the flow."""
        ...

    @abstractmethod
    async def decide(
        self, *, credential: BrowserSessionCredential, command: DecideHumanOAuthConsentCommand
    ) -> OAuthConsentContinuationDTO:
        """Recheck Alice's access and submit her decision without automatic retries.

        Approval captures the credential version before browser verification and
        checks it again afterward. Inspection and denial never initialize it.
        An uncertain provider response does not establish a confirmed denial.
        """
        ...
