from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

import pytest

from inframeld_backend.access.domain.entities.identity_recovery import IdentityRecovery
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)
from inframeld_backend.access.domain.errors.identity_recovery_errors import (
    IdentityRecoveryTransitionError,
)
from inframeld_backend.access.domain.value_objects.identity_authority import (
    IdentityAuthority,
)
from inframeld_backend.access.domain.value_objects.identity_recovery_flow_id import (
    IdentityRecoveryFlowId,
)
from inframeld_backend.access.domain.value_objects.identity_subject import (
    IdentitySubject,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

INSTALLATION = InstallationId(UUID(int=1))
AUTHORITY = IdentityAuthority("kratos")
FLOW = IdentityRecoveryFlowId(UUID(int=2))
SUBJECT = IdentitySubject(str(UUID(int=3)))
RELEASED_AT = datetime(2026, 10, 23, 12, tzinfo=UTC)

PENDING = IdentityRecoveryCleanupState.PENDING
CONFIRMED = IdentityRecoveryCleanupState.CONFIRMED
FAILED = IdentityRecoveryCleanupState.FAILED
UNCERTAIN = IdentityRecoveryCleanupState.UNCERTAIN

INCOMPLETE_STATES = [
    (PENDING, PENDING),
    (CONFIRMED, PENDING),
    (PENDING, CONFIRMED),
    (CONFIRMED, FAILED),
    (UNCERTAIN, CONFIRMED),
]


def recovery(
    *,
    installation_id: InstallationId = INSTALLATION,
    authority: IdentityAuthority = AUTHORITY,
    flow_id: IdentityRecoveryFlowId = FLOW,
    kratos: IdentityRecoveryCleanupState = PENDING,
    hydra: IdentityRecoveryCleanupState = PENDING,
    released_at: datetime | None = None,
) -> IdentityRecovery:
    return IdentityRecovery(
        installation_id=installation_id,
        authority=authority,
        flow_id=flow_id,
        subject=SUBJECT,
        kratos_cleanup_state=kratos,
        hydra_cleanup_state=hydra,
        released_at=released_at,
    )


def test_new_recovery_starts_with_both_cleanup_obligations_pending() -> None:
    operation = recovery()

    assert operation.installation_id == INSTALLATION
    assert operation.authority == AUTHORITY
    assert operation.flow_id == FLOW
    assert operation.subject == SUBJECT
    assert operation.kratos_cleanup_state is PENDING
    assert operation.hydra_cleanup_state is PENDING
    assert operation.is_cleanup_confirmed is False
    assert operation.is_released is False
    assert operation.released_at is None


@pytest.mark.parametrize("provider", ["kratos", "hydra"])
@pytest.mark.parametrize("outcome", [FAILED, UNCERTAIN, CONFIRMED])
def test_provider_outcomes_are_recorded_independently(
    provider: Literal["kratos", "hydra"],
    outcome: IdentityRecoveryCleanupState,
) -> None:
    """Success or failure at one provider says nothing about the other."""
    operation = recovery()

    if provider == "kratos":
        operation.record_kratos_cleanup(outcome)
        assert operation.kratos_cleanup_state is outcome
        assert operation.hydra_cleanup_state is PENDING
    else:
        operation.record_hydra_cleanup(outcome)
        assert operation.hydra_cleanup_state is outcome
        assert operation.kratos_cleanup_state is PENDING

    assert operation.is_cleanup_confirmed is False
    assert operation.is_released is False


@pytest.mark.parametrize("provider", ["kratos", "hydra"])
@pytest.mark.parametrize("previous_outcome", [FAILED, UNCERTAIN])
def test_reconciliation_can_confirm_previously_unfinished_cleanup(
    provider: Literal["kratos", "hydra"],
    previous_outcome: IdentityRecoveryCleanupState,
) -> None:
    """Later trusted evidence can resolve an earlier failure or unknown outcome."""
    operation = recovery()
    record = (
        operation.record_kratos_cleanup if provider == "kratos" else operation.record_hydra_cleanup
    )

    record(previous_outcome)
    record(CONFIRMED)

    if provider == "kratos":
        assert operation.kratos_cleanup_state is CONFIRMED
        assert operation.hydra_cleanup_state is PENDING
    else:
        assert operation.hydra_cleanup_state is CONFIRMED
        assert operation.kratos_cleanup_state is PENDING


@pytest.mark.parametrize("provider", ["kratos", "hydra"])
@pytest.mark.parametrize("later_outcome", [PENDING, FAILED, UNCERTAIN])
def test_confirmed_cleanup_cannot_regress(
    provider: Literal["kratos", "hydra"],
    later_outcome: IdentityRecoveryCleanupState,
) -> None:
    """A late unsuccessful report cannot erase confirmed cleanup evidence."""
    operation = recovery()
    record = (
        operation.record_kratos_cleanup if provider == "kratos" else operation.record_hydra_cleanup
    )
    record(CONFIRMED)

    with pytest.raises(IdentityRecoveryTransitionError):
        record(later_outcome)

    if provider == "kratos":
        assert operation.kratos_cleanup_state is CONFIRMED
        assert operation.hydra_cleanup_state is PENDING
    else:
        assert operation.hydra_cleanup_state is CONFIRMED
        assert operation.kratos_cleanup_state is PENDING


@pytest.mark.parametrize("provider", ["kratos", "hydra"])
def test_pending_is_not_a_provider_result(
    provider: Literal["kratos", "hydra"],
) -> None:
    operation = recovery()
    record = (
        operation.record_kratos_cleanup if provider == "kratos" else operation.record_hydra_cleanup
    )

    with pytest.raises(IdentityRecoveryTransitionError):
        record(PENDING)

    assert operation.kratos_cleanup_state is PENDING
    assert operation.hydra_cleanup_state is PENDING


def test_confirming_both_providers_does_not_automatically_release_the_block() -> None:
    """The application must separately check current eligibility and other recoveries."""
    operation = recovery()

    operation.record_kratos_cleanup(CONFIRMED)
    operation.record_hydra_cleanup(CONFIRMED)

    assert operation.is_cleanup_confirmed is True
    assert operation.is_released is False
    assert operation.released_at is None


@pytest.mark.parametrize(("kratos", "hydra"), INCOMPLETE_STATES)
def test_incomplete_cleanup_cannot_release_the_block(
    kratos: IdentityRecoveryCleanupState,
    hydra: IdentityRecoveryCleanupState,
) -> None:
    operation = recovery(kratos=kratos, hydra=hydra)

    with pytest.raises(IdentityRecoveryTransitionError):
        operation.release_product_block(at=RELEASED_AT)

    assert operation.kratos_cleanup_state is kratos
    assert operation.hydra_cleanup_state is hydra
    assert operation.is_released is False
    assert operation.released_at is None


def test_release_records_the_time_after_both_providers_are_confirmed() -> None:
    operation = recovery(kratos=CONFIRMED, hydra=CONFIRMED)

    operation.release_product_block(at=RELEASED_AT)

    assert operation.is_released is True
    assert operation.released_at == RELEASED_AT


def test_duplicate_completion_preserves_the_original_release_time() -> None:
    """Replaying completion must not turn the original recovery into new work."""
    operation = recovery(kratos=CONFIRMED, hydra=CONFIRMED)
    operation.release_product_block(at=RELEASED_AT)

    operation.record_kratos_cleanup(CONFIRMED)
    operation.record_hydra_cleanup(CONFIRMED)
    operation.release_product_block(at=datetime(2026, 10, 24, 12, tzinfo=UTC))

    assert operation.released_at == RELEASED_AT


@pytest.mark.parametrize(("kratos", "hydra"), INCOMPLETE_STATES)
def test_reconstitution_rejects_release_without_confirmed_cleanup(
    kratos: IdentityRecoveryCleanupState,
    hydra: IdentityRecoveryCleanupState,
) -> None:
    """Stored inconsistent state must not become a valid domain object."""
    with pytest.raises(ValueError, match="confirmed"):
        recovery(
            kratos=kratos,
            hydra=hydra,
            released_at=RELEASED_AT,
        )


def test_reconstitution_preserves_completed_history() -> None:
    operation = recovery(
        kratos=CONFIRMED,
        hydra=CONFIRMED,
        released_at=RELEASED_AT,
    )

    assert operation.is_cleanup_confirmed is True
    assert operation.is_released is True
    assert operation.released_at == RELEASED_AT


def test_release_rejects_a_timestamp_without_timezone_information() -> None:
    operation = recovery(kratos=CONFIRMED, hydra=CONFIRMED)

    with pytest.raises(ValueError, match="timezone"):
        operation.release_product_block(at=datetime(2026, 10, 23, 12))

    assert operation.released_at is None


def test_reconstitution_rejects_a_release_time_without_timezone_information() -> None:
    with pytest.raises(ValueError, match="timezone"):
        recovery(
            kratos=CONFIRMED,
            hydra=CONFIRMED,
            released_at=datetime(2026, 10, 23, 12),
        )


def test_identity_does_not_change_when_cleanup_progresses() -> None:
    pending = recovery()
    completed = recovery(
        kratos=CONFIRMED,
        hydra=CONFIRMED,
        released_at=RELEASED_AT,
    )

    assert pending == completed
    assert hash(pending) == hash(completed)


@pytest.mark.parametrize(
    ("installation_id", "authority", "flow_id"),
    [
        (
            InstallationId(UUID(int=9)),
            AUTHORITY,
            FLOW,
        ),
        (
            INSTALLATION,
            IdentityAuthority("another-kratos"),
            FLOW,
        ),
        (
            INSTALLATION,
            AUTHORITY,
            IdentityRecoveryFlowId(UUID(int=9)),
        ),
    ],
)
def test_another_installation_provider_or_flow_is_a_different_recovery(
    installation_id: InstallationId,
    authority: IdentityAuthority,
    flow_id: IdentityRecoveryFlowId,
) -> None:
    assert recovery() != recovery(
        installation_id=installation_id,
        authority=authority,
        flow_id=flow_id,
    )


@pytest.mark.parametrize(
    "attribute",
    [
        "installation_id",
        "authority",
        "flow_id",
        "subject",
        "kratos_cleanup_state",
        "hydra_cleanup_state",
        "released_at",
    ],
)
def test_public_state_cannot_bypass_domain_transitions(attribute: str) -> None:
    operation = recovery()

    with pytest.raises(AttributeError):
        operation.__setattr__(attribute, None)
