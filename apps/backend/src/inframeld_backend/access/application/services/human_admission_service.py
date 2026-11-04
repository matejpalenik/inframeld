import asyncio
from typing import override
from uuid import uuid4

from inframeld_backend.access.application.commands.admit_human_command import AdmitHumanCommand
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.human_admission_authorization_dto import (
    HumanAdmissionAuthorizationDTO,
)
from inframeld_backend.access.application.dtos.human_admission_facts_dto import (
    HumanAdmissionFactsDTO,
)
from inframeld_backend.access.application.dtos.human_admission_result_dto import (
    HumanAdmissionResultDTO,
)
from inframeld_backend.access.application.dtos.organization_access_facts_dto import (
    OrganizationAccessFactsDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
)
from inframeld_backend.access.application.protocols.human_admission_facts_reader import (
    HumanAdmissionFactsReader,
)
from inframeld_backend.access.application.protocols.human_admission_result_reader import (
    HumanAdmissionResultReader,
)
from inframeld_backend.access.application.protocols.human_admission_writer import (
    HumanAdmissionWriter,
)
from inframeld_backend.access.application.protocols.human_admitter import HumanAdmitter
from inframeld_backend.access.application.protocols.human_identity_verifier import (
    HumanIdentityVerifier,
)
from inframeld_backend.access.application.services.human_admission_fingerprint_service import (
    HumanAdmissionFingerprintService,
)
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.policies.human_admission_policy import HumanAdmissionPolicy
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
)
from inframeld_backend.shared.application.dtos.operation_admission_context_dto import (
    OperationAdmissionContextDTO,
)
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    DependencyUnavailableError,
    ResourceNotFoundError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.protocols.operation_idempotency import (
    OperationIdempotency,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)


class HumanAdmissionService(HumanAdmitter):
    def __init__(
        self,
        *,
        transactions: TransactionManager,
        facts: HumanAdmissionFactsReader,
        writer: HumanAdmissionWriter,
        results: HumanAdmissionResultReader,
        idempotency: OperationIdempotency,
        fingerprints: HumanAdmissionFingerprintService,
        identity_verifier: HumanIdentityVerifier,
        identity_authority: IdentityAuthority,
        identity_timeout_seconds: float,
    ) -> None:
        self._transactions = transactions
        self._facts = facts
        self._writer = writer
        self._results = results
        self._idempotency = idempotency
        self._fingerprints = fingerprints
        self._identity_verifier = identity_verifier
        self._identity_authority = identity_authority
        self._identity_timeout_seconds = identity_timeout_seconds

    @override
    async def admit(
        self,
        *,
        access: AccessContextDTO,
        command: AdmitHumanCommand,
        context: OperationAdmissionContextDTO,
    ) -> HumanAdmissionResultDTO:
        route = f"/v1/organizations/{command.organization_id.value}/human-admissions"
        if context.method != "POST" or context.requested_route != route:
            raise RuntimeError("Human admission changed its original operation route.")
        fingerprint = self._fingerprints.for_admit(command)
        try:
            async with asyncio.timeout(5), self._transactions.begin():
                self._authorize(
                    access,
                    command.organization_id,
                    await self._facts.read_authorization(
                        access=access, organization_id=command.organization_id
                    ),
                )

            # The preliminary transaction has ended before private provider I/O.
            identity = VerifiedHumanIdentityDTO(
                self._identity_authority, IdentitySubject(str(command.identity_id))
            )
            async with asyncio.timeout(self._identity_timeout_seconds):
                verified = await self._identity_verifier.verify(
                    identity, timeout_seconds=self._identity_timeout_seconds
                )
            if verified is None:
                raise ConflictError("The requested human identity is not currently admissible.")
            if verified != identity:
                raise RuntimeError("Human identity verification changed its requested binding.")

            async with asyncio.timeout(5), self._transactions.begin():
                facts = await self._facts.read_for_admission(
                    access=access, organization_id=command.organization_id, identity=verified
                )
                if facts is None:
                    raise ResourceNotFoundError()
                scope = self._authorize(access, command.organization_id, facts.actor)
                self._require_recipient(facts, scope.organization_id, verified)
                return await self._admit_or_replay(
                    access=access,
                    command=command,
                    context=context,
                    fingerprint=fingerprint,
                    facts=facts,
                    scope=scope,
                )
        except TimeoutError:
            raise DependencyUnavailableError() from None

    @staticmethod
    def _authorize(
        access: AccessContextDTO,
        organization_id: OrganizationId,
        facts: OrganizationAccessFactsDTO | None,
    ) -> HumanAdmissionAuthorizationDTO:
        if facts is None:
            raise ResourceNotFoundError()
        if facts.principal.id != access.actor_principal_id:
            raise RuntimeError("Human admission facts changed the authenticated actor.")
        if facts.principal.organization_id != organization_id:
            raise ResourceNotFoundError()

        eligibility = PrincipalAccessEvaluationService.evaluate(
            access=access,
            principal=facts.principal,
            has_pending_recovery=facts.has_pending_recovery,
            oauth_credential_facts=facts.oauth_credential_facts,
        )
        if not eligibility.credential_is_current:
            raise HumanOAuthCredentialRejectedError()
        if not HumanAdmissionPolicy.may_authorize(
            eligibility,
            has_admit_users=any(grant.action_id.value == "admit-users" for grant in facts.grants),
        ):
            raise AccessDeniedError()
        return HumanAdmissionAuthorizationDTO(organization_id, facts.access_revision)

    @staticmethod
    def _require_recipient(
        facts: HumanAdmissionFactsDTO,
        organization_id: OrganizationId,
        identity: VerifiedHumanIdentityDTO,
    ) -> None:
        state = facts.credential_state
        if (
            facts.identity != identity
            or state.identity != identity
            or state.installation_id != facts.installation_id
        ):
            raise RuntimeError("Human admission facts changed the coordinated identity.")
        if not HumanAdmissionPolicy.may_admit(
            principal=facts.principal,
            organization_id=organization_id,
            has_pending_recovery=state.has_pending_recovery,
        ):
            raise ConflictError("The requested human identity is not currently admissible.")
        if state.version is None and facts.has_credential_history:
            raise DependencyUnavailableError()

    async def _admit_or_replay(
        self,
        *,
        access: AccessContextDTO,
        command: AdmitHumanCommand,
        context: OperationAdmissionContextDTO,
        fingerprint: RequestFingerprint,
        facts: HumanAdmissionFactsDTO,
        scope: HumanAdmissionAuthorizationDTO,
    ) -> HumanAdmissionResultDTO:
        operation = await self._idempotency.find_or_reserve(
            context=context,
            access=access,
            authorization=scope,
            fingerprint=fingerprint,
            expected_replay_kind=OperationReplayKind.SAFE_RESULT,
            lookup_authority=OperationLookupAuthority(
                OperationLookupAuthorityFamily.ORGANIZATION_ACTION_USE, ActionId("admit-users")
            ),
        )
        if not isinstance(operation, NewOperationReservationDTO):
            completed = self._completed(operation)
            original = await self._results.original(
                installation_id=facts.installation_id,
                identity=facts.identity,
                organization_id=scope.organization_id,
                actor_id=access.actor_principal_id,
                operation=completed,
            )
            if (
                original.operation != completed
                or original.installation_id != facts.installation_id
                or original.identity != facts.identity
                or original.organization_id != scope.organization_id
                or original.actor_principal_id != access.actor_principal_id
                or facts.principal is None
                or original.principal_id != facts.principal.id
            ):
                raise ConflictError("The original human admission result is incoherent.")
            return original

        if command.expected_access_revision != scope.access_revision:
            raise StaleRevisionError()
        changed = facts.principal is None
        principal = facts.principal or Principal(
            PrincipalId(uuid4()), scope.organization_id, PrincipalKind.HUMAN, PrincipalStatus.ACTIVE
        )
        await self._writer.save(
            facts=facts,
            principal=principal,
            actor_id=access.actor_principal_id,
            operation_id=operation.operation_id,
        )
        completed = self._completed(
            await self._idempotency.record_completed_result(
                operation, replay_kind=OperationReplayKind.SAFE_RESULT
            )
        )
        if completed.operation_id != operation.operation_id:
            raise RuntimeError("Human admission completion changed the original operation.")
        return HumanAdmissionResultDTO(
            facts.installation_id,
            facts.identity,
            scope.organization_id,
            access.actor_principal_id,
            principal.id,
            scope.access_revision + int(changed),
            changed,
            completed,
        )

    @staticmethod
    def _completed(operation: object) -> CompletedSynchronousOperationDTO:
        if (
            not isinstance(operation, CompletedSynchronousOperationDTO)
            or operation.replay_kind is not OperationReplayKind.SAFE_RESULT
        ):
            raise ConflictError("Human admission has no safe completed result.")
        return operation
