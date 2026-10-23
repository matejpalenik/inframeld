from datetime import datetime
from typing import override

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


class IdentityRecovery:
    """Keep the cleanup checklist for one account recovery.

    When Alice resets her password, Kratos must invalidate her old browser
    sessions and Hydra her old CLI credentials. Record each result and prevent
    releasing this recovery's access block until both are confirmed.

    The service performs the cleanup and checks whether Alice may regain access.
    """

    def __init__(
        self,
        *,
        installation_id: InstallationId,
        authority: IdentityAuthority,
        flow_id: IdentityRecoveryFlowId,
        subject: IdentitySubject,
        kratos_cleanup_state: IdentityRecoveryCleanupState = (IdentityRecoveryCleanupState.PENDING),
        hydra_cleanup_state: IdentityRecoveryCleanupState = (IdentityRecoveryCleanupState.PENDING),
        released_at: datetime | None = None,
    ) -> None:
        if released_at is not None:
            if (
                kratos_cleanup_state is not IdentityRecoveryCleanupState.CONFIRMED
                or hydra_cleanup_state is not IdentityRecoveryCleanupState.CONFIRMED
            ):
                raise ValueError("Released recovery requires both cleanup outcomes confirmed.")

            if released_at.utcoffset() is None:
                raise ValueError("The release time must include timezone information.")

        self._installation_id = installation_id
        self._authority = authority
        self._flow_id = flow_id
        self._subject = subject
        self._kratos_cleanup_state = kratos_cleanup_state
        self._hydra_cleanup_state = hydra_cleanup_state
        self._released_at = released_at

    @property
    def identity(
        self,
    ) -> tuple[InstallationId, IdentityAuthority, IdentityRecoveryFlowId]:
        return self._installation_id, self._authority, self._flow_id

    @property
    def installation_id(self) -> InstallationId:
        return self._installation_id

    @property
    def authority(self) -> IdentityAuthority:
        return self._authority

    @property
    def flow_id(self) -> IdentityRecoveryFlowId:
        return self._flow_id

    @property
    def subject(self) -> IdentitySubject:
        return self._subject

    @property
    def kratos_cleanup_state(self) -> IdentityRecoveryCleanupState:
        return self._kratos_cleanup_state

    @property
    def hydra_cleanup_state(self) -> IdentityRecoveryCleanupState:
        return self._hydra_cleanup_state

    @property
    def released_at(self) -> datetime | None:
        return self._released_at

    @property
    def is_cleanup_confirmed(self) -> bool:
        return (
            self._kratos_cleanup_state is IdentityRecoveryCleanupState.CONFIRMED
            and self._hydra_cleanup_state is IdentityRecoveryCleanupState.CONFIRMED
        )

    @property
    def is_released(self) -> bool:
        return self._released_at is not None

    def record_kratos_cleanup(self, outcome: IdentityRecoveryCleanupState) -> None:
        """Record trusted native-cleanup evidence without changing Hydra's outcome."""
        self._kratos_cleanup_state = self._next_cleanup_state(
            current=self._kratos_cleanup_state,
            outcome=outcome,
        )

    def record_hydra_cleanup(self, outcome: IdentityRecoveryCleanupState) -> None:
        """Record Hydra cleanup evidence without changing Kratos's outcome."""
        self._hydra_cleanup_state = self._next_cleanup_state(
            current=self._hydra_cleanup_state,
            outcome=outcome,
        )

    def release_product_block(self, *, at: datetime) -> None:
        """Release this operation after the application checks current eligibility.

        The caller must also check competing recovery obligations under the
        required coordination locks. Provider confirmation alone does not
        establish those conditions.

        Repeated release preserves the original timestamp.

        Raises:
            IdentityRecoveryTransitionError: Either provider remains unconfirmed.
            ValueError: A new release timestamp has no timezone information.
        """
        if self.is_released:
            return

        if not self.is_cleanup_confirmed:
            raise IdentityRecoveryTransitionError(
                "Both provider cleanup outcomes must be confirmed before release."
            )

        if at.utcoffset() is None:
            raise ValueError("The release time must include timezone information.")

        self._released_at = at

    @staticmethod
    def _next_cleanup_state(
        *,
        current: IdentityRecoveryCleanupState,
        outcome: IdentityRecoveryCleanupState,
    ) -> IdentityRecoveryCleanupState:
        if outcome is IdentityRecoveryCleanupState.PENDING:
            raise IdentityRecoveryTransitionError("Pending is not a provider cleanup outcome.")

        if (
            current is IdentityRecoveryCleanupState.CONFIRMED
            and outcome is not IdentityRecoveryCleanupState.CONFIRMED
        ):
            raise IdentityRecoveryTransitionError(
                "Confirmed provider cleanup cannot be replaced by an unfinished outcome."
            )

        return outcome

    @override
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, IdentityRecovery):
            return NotImplemented
        return self.identity == other.identity

    @override
    def __hash__(self) -> int:
        return hash(self.identity)
