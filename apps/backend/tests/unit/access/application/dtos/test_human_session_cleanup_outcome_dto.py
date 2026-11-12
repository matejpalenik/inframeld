from typing import cast

import pytest

from inframeld_backend.access.application.dtos.human_session_cleanup_outcome_dto import (
    HumanSessionCleanupOutcomeDTO,
)
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState as State,
)


@pytest.mark.parametrize(
    "state,status",
    [
        (State.PENDING, None),
        (State.CONFIRMED, None),
        (State.CONFIRMED, 200),
        (State.CONFIRMED, 404),
        (State.UNCERTAIN, True),
        (State.UNCERTAIN, 99),
        (State.UNCERTAIN, 600),
        (State.UNCERTAIN, 1.5),
        (State.FAILED, None),
        (State.FAILED, 204),
        (State.FAILED, 408),
        (State.FAILED, 500),
    ],
)
def test_incoherent_or_pending_provider_observations_are_rejected(
    state: State, status: object
) -> None:
    with pytest.raises(ValueError):
        HumanSessionCleanupOutcomeDTO(state, cast(int | None, status))


@pytest.mark.parametrize(
    "state,status",
    [
        (State.CONFIRMED, 204),
        (State.FAILED, 404),
        (State.FAILED, 429),
        (State.UNCERTAIN, None),
        (State.UNCERTAIN, 204),
        (State.UNCERTAIN, 408),
        (State.UNCERTAIN, 501),
        (State.UNCERTAIN, 505),
    ],
)
def test_safe_observations_do_not_claim_retry_permission(state: State, status: int | None) -> None:
    result = HumanSessionCleanupOutcomeDTO(state, status)
    assert result.state is state and result.http_status == status
