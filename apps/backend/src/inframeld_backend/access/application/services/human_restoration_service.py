import asyncio
from dataclasses import replace
from typing import override

from inframeld_backend.access.application.commands.restore_human_command import RestoreHumanCommand
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.human_lifecycle_facts_dto import (
    HumanLifecycleFactsDTO,
)
from inframeld_backend.access.application.dtos.human_restoration_result_dto import (
    HumanRestorationResultDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
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
from inframeld_backend.access.application.protocols.human_restorer import HumanRestorer
from inframeld_backend.access.application.services.human_lifecycle_fingerprint_service import (
    HumanLifecycleFingerprintService,
)
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.domain.enums.organization_action import OrganizationAction
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.policies.principal_access_policy import PrincipalAccessPolicy
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
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
from inframeld_backend.shared.domain.errors.domain_errors import InvalidStateTransitionError
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class HumanRestorationService(HumanRestorer):
    """Verify the stable identity, then atomically restore and advance its version."""

    def __init__(
        self,
        *,
        transaction_manager: TransactionManager,
        lifecycle_facts_reader: HumanLifecycleFactsReader,
        lifecycle_writer: HumanLifecycleWriter,
        lifecycle_result_reader: HumanLifecycleResultReader,
        operation_idempotency: OperationIdempotency,
        lifecycle_fingerprint_service: HumanLifecycleFingerprintService,
        identity_verifier: HumanIdentityVerifier,
    ) -> None:
        self._transaction_manager = transaction_manager
        self._lifecycle_facts_reader = lifecycle_facts_reader
        self._lifecycle_writer = lifecycle_writer
        self._lifecycle_result_reader = lifecycle_result_reader
        self._operation_idempotency = operation_idempotency
        self._lifecycle_fingerprint_service = lifecycle_fingerprint_service
        self._identity_verifier = identity_verifier

    @override
    async def restore(
        self,
        *,
        access: AccessContextDTO,
        command: RestoreHumanCommand,
        context: IdempotencyContextDTO,
    ) -> HumanRestorationResultDTO:
        route = f"/v1/organizations/{command.organization_id.value}/humans/{command.principal_id.value}/restore"
        if context.method is not HttpMethod.POST or context.requested_route != route:
            raise RuntimeError("Restoration changed its original method or route.")
        action = ActionId(OrganizationAction.RESTORE_USERS.value)
        fingerprint = self._lifecycle_fingerprint_service.for_restore(command)
        try:
            async with asyncio.timeout(5), self._transaction_manager.begin():
                preliminary = self._require_facts(
                    facts=await self._lifecycle_facts_reader.read_authorization(
                        access=access,
                        organization_id=command.organization_id,
                        principal_id=command.principal_id,
                        action_id=action,
                    ),
                    access=access,
                    organization_id=command.organization_id,
                    principal_id=command.principal_id,
                    action=action,
                )
            identity = preliminary.target_identity
            assert identity is not None
            # Same-identity provider observation occurs after the preliminary transaction.
            async with asyncio.timeout(5):
                verified = await self._identity_verifier.verify(identity, timeout_seconds=5)
            if verified != identity:
                raise ConflictError("The reviewed stable identity is not currently verified.")
            async with asyncio.timeout(5), self._transaction_manager.begin():
                facts = self._require_facts(
                    facts=await self._lifecycle_facts_reader.lock_for_change(
                        access=access,
                        organization_id=command.organization_id,
                        principal_id=command.principal_id,
                        action_id=action,
                        identity=identity,
                    ),
                    access=access,
                    organization_id=command.organization_id,
                    principal_id=command.principal_id,
                    action=action,
                    expected_identity=identity,
                )
                operation = await self._operation_idempotency.reserve_or_recover(
                    context=context,
                    access=access,
                    authorization=facts,
                    fingerprint=fingerprint,
                    expected_replay_kind=OperationReplayKind.SAFE_RESULT,
                    lookup_authority=OperationLookupAuthority(
                        OperationLookupAuthorityFamily.ORGANIZATION_ACTION_USE, action
                    ),
                )
                if not isinstance(operation, NewOperationReservationDTO):
                    if (
                        not isinstance(operation, CompletedSynchronousOperationDTO)
                        or operation.replay_kind is not OperationReplayKind.SAFE_RESULT
                    ):
                        raise ConflictError("The original restoration has no safe outcome.")
                    original = await self._lifecycle_result_reader.restoration_original(
                        facts=facts, command=command, operation=operation
                    )
                    if (
                        original is None
                        or original.organization_id != facts.organization_id
                        or original.principal_id != command.principal_id
                        or original.actor_principal_id != access.actor_principal_id
                        or type(original.access_revision) is not int
                        or not 0 <= original.access_revision <= RevisionValidation.MAX_VALUE
                        or original.operation.operation_id != operation.operation_id
                    ):
                        raise ConflictError("The original restoration binding is unavailable.")
                    return replace(original, operation=operation)
                if command.expected_access_revision != facts.access_revision:
                    raise StaleRevisionError()
                target = facts.target
                assert target is not None
                if not facts.required_cleanup_confirmed or facts.has_newer_recovery_block:
                    raise ConflictError(
                        "Required cleanup or a newer recovery restriction prevents restoration."
                    )
                cleanup = facts.current_suspension
                if cleanup is not None:
                    if (
                        cleanup.organization_id,
                        cleanup.principal_id,
                        cleanup.installation_id,
                        cleanup.authority,
                        cleanup.subject,
                    ) != (
                        facts.organization_id,
                        target.id,
                        facts.installation_id,
                        identity.authority,
                        identity.subject,
                    ):
                        raise ConflictError("Required cleanup changed its original scope.")
                    if not cleanup.is_cleanup_confirmed:
                        raise ConflictError("The original suspension cleanup is incomplete.")
                elif target.status is PrincipalStatus.SUSPENDED:
                    raise DependencyUnavailableError("Required original cleanup is unavailable.")
                version = facts.target_version
                if version is None:
                    raise DependencyUnavailableError(
                        "The original credential version is unavailable."
                    )
                try:
                    restored = target.restore()
                except InvalidStateTransitionError as error:
                    raise ConflictError("The target cannot be restored.") from error
                changed = restored.status is not target.status
                if changed and (
                    version.value == 2**63 - 1
                    or facts.access_revision == RevisionValidation.MAX_VALUE
                ):
                    raise ConflictError(
                        "The original security version or Access revision cannot advance."
                    )
                after_version = HumanCredentialVersion(version.value + int(changed))
                await self._lifecycle_writer.save_restoration(
                    facts=facts,
                    command=command,
                    target=restored,
                    version=after_version,
                    operation=operation,
                )
                completed = await self._operation_idempotency.record_completed_result(
                    operation, replay_kind=OperationReplayKind.SAFE_RESULT
                )
                if (
                    not isinstance(completed, CompletedSynchronousOperationDTO)
                    or completed.replay_kind is not OperationReplayKind.SAFE_RESULT
                    or completed.operation_id != operation.operation_id
                ):
                    raise ConflictError("Restoration completion changed its operation.")
                result = HumanRestorationResultDTO(
                    facts.organization_id,
                    target.id,
                    access.actor_principal_id,
                    facts.access_revision + int(changed),
                    after_version,
                    completed,
                )
                await self._lifecycle_writer.save_result(facts=facts, result=result)
                return result
        except TimeoutError as error:
            raise DependencyUnavailableError() from error

    @staticmethod
    def _require_facts(
        *,
        facts: HumanLifecycleFactsDTO | None,
        access: AccessContextDTO,
        organization_id: OrganizationId,
        principal_id: PrincipalId,
        action: ActionId,
        expected_identity: VerifiedHumanIdentityDTO | None = None,
    ) -> HumanLifecycleFactsDTO:
        if facts is None:
            raise ResourceNotFoundError()
        if (
            facts.organization_id != organization_id
            or facts.actor.id != access.actor_principal_id
            or facts.actor.organization_id != organization_id
            or facts.action_id != action
            or type(facts.access_revision) is not int
            or not 0 <= facts.access_revision <= RevisionValidation.MAX_VALUE
        ):
            raise RuntimeError("Lifecycle facts changed the current actor, action or Organization.")
        PrincipalAccessEvaluationService.require_human(access=access, principal=facts.actor)
        if facts.actor_credential_facts is None:
            raise DependencyUnavailableError("Current human credential facts are unavailable.")
        eligibility = PrincipalAccessEvaluationService.evaluate(
            access=access,
            principal=facts.actor,
            has_pending_recovery=facts.actor_has_pending_recovery,
            oauth_credential_facts=facts.actor_credential_facts,
        )
        PrincipalAccessEvaluationService.require_current_credential(
            access=access, principal_access=eligibility
        )
        if not PrincipalAccessPolicy.may_use_product(eligibility) or not facts.actor_has_action:
            raise AccessDeniedError()
        target = facts.target
        if target is None or target.id != principal_id or target.organization_id != organization_id:
            raise ResourceNotFoundError()
        if target.kind is not PrincipalKind.HUMAN:
            raise ConflictError("Lifecycle changes require an admitted human target.")
        if facts.target_identity is None:
            raise DependencyUnavailableError("The stable target identity is unavailable.")
        if expected_identity is not None and facts.target_identity != expected_identity:
            raise ConflictError("The target identity changed during verification.")
        return facts
