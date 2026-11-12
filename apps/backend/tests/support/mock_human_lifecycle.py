from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from typing import override
from uuid import UUID

from inframeld_backend.access.application.commands.restore_human_command import RestoreHumanCommand
from inframeld_backend.access.application.commands.suspend_human_command import SuspendHumanCommand
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.browser_session_authentication_dto import (
    BrowserSessionAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.human_credential_facts_dto import (
    HumanCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.human_lifecycle_facts_dto import (
    HumanLifecycleFactsDTO,
)
from inframeld_backend.access.application.dtos.human_restoration_result_dto import (
    HumanRestorationResultDTO,
)
from inframeld_backend.access.application.dtos.human_suspension_result_dto import (
    HumanSuspensionResultDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.authorized_operation_scope import (
    AuthorizedOperationScope,
)
from inframeld_backend.access.application.protocols.human_identity_verifier import (
    HumanIdentityVerifier,
)
from inframeld_backend.access.application.protocols.human_lifecycle_facts_reader import (
    HumanLifecycleFactsReader,
)
from inframeld_backend.access.application.protocols.human_lifecycle_result_reader import (
    HumanLifecycleResultReader,
)
from inframeld_backend.access.application.protocols.human_lifecycle_writer import (
    HumanLifecycleWriter,
)
from inframeld_backend.access.application.services.human_lifecycle_fingerprint_service import (
    HumanLifecycleFingerprintService,
)
from inframeld_backend.access.application.services.human_restoration_service import (
    HumanRestorationService,
)
from inframeld_backend.access.application.services.human_suspension_service import (
    HumanSuspensionService,
)
from inframeld_backend.access.application.value_objects.security_review_reference import (
    SecurityReviewReference,
)
from inframeld_backend.access.application.value_objects.suspension_reason import SuspensionReason
from inframeld_backend.access.domain.entities.human_suspension import HumanSuspension
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState as State,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.human_suspension_id import HumanSuspensionId
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.accepted_async_operation_dto import (
    AcceptedAsyncOperationDTO,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
)
from inframeld_backend.shared.application.dtos.recovery_required_operation_dto import (
    RecoveryRequiredOperationDTO,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.protocols.operation_idempotency import (
    OperationIdempotency,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from tests.support.mock_project_metadata import ACCESS, ORGANIZATION_ID

_evidence = ACCESS.authentication_evidence
assert isinstance(_evidence, BrowserSessionAuthenticationDTO)
EVIDENCE: BrowserSessionAuthenticationDTO = _evidence
IDENTITY = VerifiedHumanIdentityDTO(EVIDENCE.identity.authority, IdentitySubject(str(UUID(int=44))))
TARGET = Principal(
    PrincipalId(UUID(int=42)), ORGANIZATION_ID, PrincipalKind.HUMAN, PrincipalStatus.ACTIVE
)
ACTOR = Principal(
    ACCESS.actor_principal_id, ORGANIZATION_ID, PrincipalKind.HUMAN, PrincipalStatus.ACTIVE
)
VERSION = HumanCredentialVersion(5)
OPERATION = OperationId("human-lifecycle-original")
REQUEST_ID = RequestId(UUID(int=52))
ASYNC = AcceptedAsyncOperationDTO(OPERATION, False, None)
SYNC = CompletedSynchronousOperationDTO(
    OPERATION, False, OperationReplayKind.SAFE_RESULT, datetime(2030, 1, 1, tzinfo=UTC)
)
SUSPEND = SuspendHumanCommand(ORGANIZATION_ID, TARGET.id, 7, SuspensionReason("Incident reviewed"))
RESTORE = RestoreHumanCommand(
    ORGANIZATION_ID, TARGET.id, 7, SecurityReviewReference("security-review/42")
)


def context(restoring: bool = False) -> IdempotencyContextDTO:
    from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey

    return IdempotencyContextDTO(
        HttpMethod.POST,
        f"/v1/organizations/{ORGANIZATION_ID.value}/humans/{TARGET.id.value}/{'restore' if restoring else 'suspend'}",
        IdempotencyKey("lifecycle-request"),
    )


def suspension(confirmed: bool = False) -> HumanSuspension:
    state = State.CONFIRMED if confirmed else State.PENDING
    return HumanSuspension(
        id=HumanSuspensionId(UUID(int=50)),
        organization_id=ORGANIZATION_ID,
        principal_id=TARGET.id,
        installation_id=EVIDENCE.installation_id,
        authority=IDENTITY.authority,
        subject=IDENTITY.subject,
        kratos_sessions=state,
        hydra_cli_grants=state,
        hydra_remembered_logins=state,
    )


class MockHumanLifecycle(
    HumanLifecycleFactsReader,
    HumanLifecycleWriter,
    HumanLifecycleResultReader,
    TransactionManager,
    OperationIdempotency,
    HumanIdentityVerifier,
):
    """Control lifecycle decisions and transaction acknowledgment without SQL or providers."""

    def __init__(self, *, restoring: bool = False) -> None:
        self.events: list[str] = []
        self.restoring = restoring
        self.suspension_command: SuspendHumanCommand | None = None
        self.restoration_command: RestoreHumanCommand | None = None
        self.facts: HumanLifecycleFactsDTO | None = HumanLifecycleFactsDTO(
            EVIDENCE.installation_id,
            ORGANIZATION_ID,
            7,
            ActionId("restore-users" if restoring else "suspend-users"),
            ACTOR,
            False,
            HumanCredentialFactsDTO(True, EVIDENCE.version),
            True,
            replace(TARGET, status=PrincipalStatus.SUSPENDED) if restoring else TARGET,
            IDENTITY,
            VERSION,
            suspension(True) if restoring else None,
            restoring,
            False,
        )
        self.final_facts: HumanLifecycleFactsDTO | None = None
        self.replay: (
            NewOperationReservationDTO
            | CompletedSynchronousOperationDTO
            | AcceptedAsyncOperationDTO
            | RecoveryRequiredOperationDTO
        ) = NewOperationReservationDTO(OPERATION)
        self.suspension_result: HumanSuspensionResultDTO | None = None
        self.restoration_result: HumanRestorationResultDTO | None = None
        self.in_transaction = False
        self.provider_missing = False
        self.provider_identity: VerifiedHumanIdentityDTO = IDENTITY
        self.provider_error: Exception | None = None
        self.save_error: BaseException | None = None
        self.completion_error: Exception | None = None
        self.commit_unknown = False
        self.writes: list[tuple[str, Principal, HumanSuspension | HumanCredentialVersion]] = []
        self.committed: list[tuple[str, Principal, HumanSuspension | HumanCredentialVersion]] = []
        self._pending: list[tuple[str, Principal, HumanSuspension | HumanCredentialVersion]] = []

    def suspend_service(self) -> HumanSuspensionService:
        return HumanSuspensionService(
            transaction_manager=self,
            lifecycle_facts_reader=self,
            lifecycle_writer=self,
            lifecycle_result_reader=self,
            operation_idempotency=self,
            lifecycle_fingerprint_service=HumanLifecycleFingerprintService(
                RequestFingerprintService(RequestFingerprintKey(b"s" * 32))
            ),
        )

    def restore_service(self) -> HumanRestorationService:
        return HumanRestorationService(
            transaction_manager=self,
            lifecycle_facts_reader=self,
            lifecycle_writer=self,
            lifecycle_result_reader=self,
            operation_idempotency=self,
            lifecycle_fingerprint_service=HumanLifecycleFingerprintService(
                RequestFingerprintService(RequestFingerprintKey(b"s" * 32))
            ),
            identity_verifier=self,
        )

    @override
    @asynccontextmanager
    async def begin(self) -> AsyncGenerator[None]:
        assert not self.in_transaction
        self.events.append("begin")
        self.in_transaction = True
        try:
            yield
        except BaseException:
            self.events.append("rollback")
            self._pending.clear()
            raise
        else:
            self.committed.extend(self._pending)
            self._pending.clear()
            if self.commit_unknown and self.writes:
                self.events.append("commit-unknown")
                raise DependencyUnavailableError("Commit acknowledgment is unknown.")
            self.events.append("commit")
        finally:
            self.in_transaction = False

    @override
    async def read_authorization(
        self,
        *,
        access: AccessContextDTO,
        organization_id: OrganizationId,
        principal_id: PrincipalId,
        action_id: ActionId,
    ) -> HumanLifecycleFactsDTO | None:
        self.events.append("preauthorization")
        return self.facts

    @override
    async def lock_for_change(
        self,
        *,
        access: AccessContextDTO,
        organization_id: OrganizationId,
        principal_id: PrincipalId,
        action_id: ActionId,
        identity: VerifiedHumanIdentityDTO,
    ) -> HumanLifecycleFactsDTO | None:
        self.events.append("identity-org-fresh")
        assert self.in_transaction
        return self.final_facts if self.final_facts is not None else self.facts

    @override
    async def verify(
        self, identity: VerifiedHumanIdentityDTO, *, timeout_seconds: float
    ) -> VerifiedHumanIdentityDTO | None:
        self.events.append("verify")
        assert not self.in_transaction
        assert identity == IDENTITY and timeout_seconds <= 5
        if self.provider_error is not None:
            raise self.provider_error
        return None if self.provider_missing else self.provider_identity

    @override
    async def save_suspension(
        self,
        *,
        facts: HumanLifecycleFactsDTO,
        command: SuspendHumanCommand,
        target: Principal,
        suspension: HumanSuspension,
        operation: NewOperationReservationDTO,
        request_id: RequestId,
    ) -> None:
        self.suspension_command = command
        self.events.append("save-suspension")
        if self.save_error is not None:
            raise self.save_error
        write = ("suspend", target, suspension)
        self.writes.append(write)
        self._pending.append(write)

    @override
    async def save_restoration(
        self,
        *,
        facts: HumanLifecycleFactsDTO,
        command: RestoreHumanCommand,
        target: Principal,
        version: HumanCredentialVersion,
        operation: NewOperationReservationDTO,
    ) -> None:
        self.restoration_command = command
        self.events.append("save-restoration")
        if self.save_error is not None:
            raise self.save_error
        write = ("restore", target, version)
        self.writes.append(write)
        self._pending.append(write)

    @override
    async def save_result(
        self,
        *,
        facts: HumanLifecycleFactsDTO,
        result: HumanSuspensionResultDTO | HumanRestorationResultDTO,
    ) -> None:
        self.events.append("save-result")
        if isinstance(result, HumanSuspensionResultDTO):
            self.suspension_result = result
        else:
            self.restoration_result = result

    @override
    async def suspension_original(
        self,
        *,
        facts: HumanLifecycleFactsDTO,
        command: SuspendHumanCommand,
        operation: AcceptedAsyncOperationDTO,
    ) -> HumanSuspensionResultDTO | None:
        self.events.append("original")
        return self.suspension_result

    @override
    async def restoration_original(
        self,
        *,
        facts: HumanLifecycleFactsDTO,
        command: RestoreHumanCommand,
        operation: CompletedSynchronousOperationDTO,
    ) -> HumanRestorationResultDTO | None:
        self.events.append("original")
        return self.restoration_result

    @override
    async def reserve_or_recover[ProjectScope: ProjectId | None](
        self,
        *,
        context: IdempotencyContextDTO,
        access: AccessContextDTO,
        authorization: AuthorizedOperationScope[ProjectScope],
        fingerprint: RequestFingerprint,
        expected_replay_kind: OperationReplayKind,
        lookup_authority: OperationLookupAuthority | None = None,
    ) -> (
        NewOperationReservationDTO
        | CompletedSynchronousOperationDTO
        | AcceptedAsyncOperationDTO
        | RecoveryRequiredOperationDTO
    ):
        self.events.append("reserve")
        assert expected_replay_kind is (
            OperationReplayKind.SAFE_RESULT if self.restoring else OperationReplayKind.ASYNC_JOB
        )
        return self.replay

    @override
    async def record_completed_result(
        self, operation: NewOperationReservationDTO, *, replay_kind: OperationReplayKind
    ) -> CompletedSynchronousOperationDTO | AcceptedAsyncOperationDTO:
        self.events.append("complete")
        if self.completion_error is not None:
            raise self.completion_error
        return replace(SYNC, created=True) if self.restoring else replace(ASYNC, created=True)
