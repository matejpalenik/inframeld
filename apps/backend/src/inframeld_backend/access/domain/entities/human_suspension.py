from typing import override

from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)
from inframeld_backend.access.domain.value_objects.human_suspension_id import HumanSuspensionId
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.domain.errors.domain_errors import InvalidStateTransitionError
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


class HumanSuspension:
    """Retain one original scope and three independent cleanup observations.

    This checklist grants no authority to dispatch or restore an account.
    """

    def __init__(
        self,
        *,
        id: HumanSuspensionId,
        organization_id: OrganizationId,
        principal_id: PrincipalId,
        installation_id: InstallationId,
        authority: IdentityAuthority,
        subject: IdentitySubject,
        kratos_sessions: IdentityRecoveryCleanupState = IdentityRecoveryCleanupState.PENDING,
        hydra_cli_grants: IdentityRecoveryCleanupState = IdentityRecoveryCleanupState.PENDING,
        hydra_remembered_logins: IdentityRecoveryCleanupState = IdentityRecoveryCleanupState.PENDING,
    ) -> None:
        self._id = id
        self._organization_id = organization_id
        self._principal_id = principal_id
        self._installation_id = installation_id
        self._authority = authority
        self._subject = subject
        self._kratos_sessions = kratos_sessions
        self._hydra_cli_grants = hydra_cli_grants
        self._hydra_remembered_logins = hydra_remembered_logins

    @property
    def id(self) -> HumanSuspensionId:
        return self._id

    @property
    def organization_id(self) -> OrganizationId:
        return self._organization_id

    @property
    def principal_id(self) -> PrincipalId:
        return self._principal_id

    @property
    def installation_id(self) -> InstallationId:
        return self._installation_id

    @property
    def authority(self) -> IdentityAuthority:
        return self._authority

    @property
    def subject(self) -> IdentitySubject:
        return self._subject

    @property
    def kratos_sessions(self) -> IdentityRecoveryCleanupState:
        return self._kratos_sessions

    @property
    def hydra_cli_grants(self) -> IdentityRecoveryCleanupState:
        return self._hydra_cli_grants

    @property
    def hydra_remembered_logins(self) -> IdentityRecoveryCleanupState:
        return self._hydra_remembered_logins

    @property
    def is_cleanup_confirmed(self) -> bool:
        return all(
            state is IdentityRecoveryCleanupState.CONFIRMED
            for state in (
                self._kratos_sessions,
                self._hydra_cli_grants,
                self._hydra_remembered_logins,
            )
        )

    def record_kratos_sessions(self, outcome: IdentityRecoveryCleanupState) -> None:
        self._kratos_sessions = self._next_outcome(self._kratos_sessions, outcome)

    def record_hydra_cli_grants(self, outcome: IdentityRecoveryCleanupState) -> None:
        self._hydra_cli_grants = self._next_outcome(self._hydra_cli_grants, outcome)

    def record_hydra_remembered_logins(self, outcome: IdentityRecoveryCleanupState) -> None:
        self._hydra_remembered_logins = self._next_outcome(self._hydra_remembered_logins, outcome)

    @staticmethod
    def _next_outcome(
        current: IdentityRecoveryCleanupState, outcome: IdentityRecoveryCleanupState
    ) -> IdentityRecoveryCleanupState:
        if outcome is IdentityRecoveryCleanupState.PENDING:
            raise InvalidStateTransitionError("Pending is not a provider cleanup outcome.")
        if (
            current is IdentityRecoveryCleanupState.CONFIRMED
            and outcome is not IdentityRecoveryCleanupState.CONFIRMED
        ):
            raise InvalidStateTransitionError("Confirmed cleanup cannot regress.")
        return outcome

    @override
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, HumanSuspension):
            return NotImplemented
        return (self.installation_id, self.id) == (other.installation_id, other.id)

    @override
    def __hash__(self) -> int:
        return hash((self.installation_id, self.id))
