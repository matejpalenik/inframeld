from pydantic import SecretStr

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
from inframeld_backend.access.application.value_objects.oauth_consent_challenge import (
    OAuthConsentChallenge,
)
from inframeld_backend.access.http.requests.human_oauth_consent_request import (
    HumanOAuthConsentRequest,
)
from inframeld_backend.access.http.responses.human_oauth_consent_decision_response import (
    HumanOAuthConsentDecisionResponse,
)
from inframeld_backend.access.http.responses.human_oauth_consent_details_response import (
    HumanOAuthConsentDetailsResponse,
)
from inframeld_backend.shared.application.errors.application_errors import InvalidInputError


class HumanOAuthConsentMapper:
    @staticmethod
    def to_query(challenge: SecretStr) -> InspectHumanOAuthConsentQuery:
        try:
            return InspectHumanOAuthConsentQuery(
                OAuthConsentChallenge(challenge.get_secret_value())
            )
        except ValueError:
            raise InvalidInputError("A consent challenge is required.") from None

    @staticmethod
    def to_command(request: HumanOAuthConsentRequest) -> DecideHumanOAuthConsentCommand:
        return DecideHumanOAuthConsentCommand(
            challenge=OAuthConsentChallenge(request.consent_challenge.get_secret_value()),
            decision=request.decision,
            remember=request.remember,
        )

    @staticmethod
    def to_details_response(
        result: HumanOAuthConsentDetailsDTO,
    ) -> HumanOAuthConsentDetailsResponse:
        return HumanOAuthConsentDetailsResponse(
            account_subject=result.identity.subject.value,
            installation=result.installation.value,
            client_id=result.client_id.value,
            requested_scopes=list(result.scopes),
            requested_audience=[value.value for value in result.audiences],
            approval_required=result.approval_required,
            remember_consent_seconds=result.remember_consent_seconds,
        )

    @staticmethod
    def to_decision_response(
        result: OAuthConsentContinuationDTO,
    ) -> HumanOAuthConsentDecisionResponse:
        return HumanOAuthConsentDecisionResponse(redirect_to=result.redirect_to)
