import pytest

from inframeld_backend.access.application.dtos.human_oauth_cleanup_outcome_dto import (
    HumanOAuthCleanupOutcomeDTO,
)
from inframeld_backend.access.application.enums.oauth_cleanup_category import OAuthCleanupCategory
from inframeld_backend.access.application.enums.oauth_cleanup_disposition import (
    OAuthCleanupDisposition,
)
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)


@pytest.mark.parametrize(
    "state,disposition",
    [
        (IdentityRecoveryCleanupState.PENDING, OAuthCleanupDisposition.RETRYABLE),
        (IdentityRecoveryCleanupState.FAILED, OAuthCleanupDisposition.NOT_NEEDED),
        (IdentityRecoveryCleanupState.CONFIRMED, OAuthCleanupDisposition.RETRYABLE),
    ],
)
def test_pending_or_incompatible_provider_observations_are_rejected(
    state: IdentityRecoveryCleanupState, disposition: OAuthCleanupDisposition
) -> None:
    with pytest.raises(ValueError):
        HumanOAuthCleanupOutcomeDTO(
            state, disposition, OAuthCleanupCategory.PROVIDER_PROTOCOL_ERROR
        )


@pytest.mark.parametrize("delay", [-1, True, float("inf"), float("nan")])
def test_invalid_safe_retry_delay_is_rejected(delay: float) -> None:
    with pytest.raises(ValueError):
        HumanOAuthCleanupOutcomeDTO(
            IdentityRecoveryCleanupState.UNCERTAIN,
            OAuthCleanupDisposition.RETRYABLE,
            OAuthCleanupCategory.PROVIDER_TIMEOUT,
            retry_after_seconds=delay,
        )
