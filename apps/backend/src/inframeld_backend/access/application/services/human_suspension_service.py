import asyncio
from dataclasses import replace
from typing import override
from uuid import uuid4

from inframeld_backend.access.application.commands.suspend_human_command import SuspendHumanCommand
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.human_lifecycle_facts_dto import (
    HumanLifecycleFactsDTO,
)
from inframeld_backend.access.application.dtos.human_suspension_result_dto import (
    HumanSuspensionResultDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
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
from inframeld_backend.access.application.protocols.human_suspender import HumanSuspender
from inframeld_backend.access.application.services.human_lifecycle_fingerprint_service import (
    HumanLifecycleFingerprintService,
)
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.domain.entities.human_suspension import HumanSuspension
from inframeld_backend.access.domain.enums.organization_action import OrganizationAction
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.policies.principal_access_policy import PrincipalAccessPolicy
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.human_suspension_id import HumanSuspensionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.dtos.accepted_async_operation_dto import (
    AcceptedAsyncOperationDTO,
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
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.errors.domain_errors import InvalidStateTransitionError
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class HumanSuspensionService(HumanSuspender):
    """Commit the immediate block and original obligation before acknowledgment."""

    def __init__(
        self,
        *,
        transaction_manager: TransactionManager,
        lifecycle_facts_reader: HumanLifecycleFactsReader,
        lifecycle_writer: HumanLifecycleWriter,
        lifecycle_result_reader: HumanLifecycleResultReader,
        operation_idempotency: OperationIdempotency,
        lifecycle_fingerprint_service: HumanLifecycleFingerprintService,
    ) -> None:
        self._transaction_manager = transaction_manager
        self._lifecycle_facts_reader = lifecycle_facts_reader
        self._lifecycle_writer = lifecycle_writer
        self._lifecycle_result_reader = lifecycle_result_reader
        self._operation_idempotency = operation_idempotency
        self._lifecycle_fingerprint_service = lifecycle_fingerprint_service

    @override
    async def suspend(
        self,
        *,
        access: AccessContextDTO,
        command: SuspendHumanCommand,
        context: IdempotencyContextDTO,
        request_id: RequestId,
    ) -> HumanSuspensionResultDTO:
        route = f"/v1/organizations/{command.organization_id.value}/humans/{command.principal_id.value}/suspend"
        if context.method is not HttpMethod.POST or context.requested_route != route:
            raise RuntimeError("Suspension changed its original method or route.")
        action = ActionId(OrganizationAction.SUSPEND_USERS.value)
        fingerprint = self._lifecycle_fingerprint_service.for_suspend(command)
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
                    expected_replay_kind=OperationReplayKind.ASYNC_JOB,
                    lookup_authority=OperationLookupAuthority(
                        OperationLookupAuthorityFamily.ORGANIZATION_ACTION_USE, action
                    ),
                )
                if not isinstance(operation, NewOperationReservationDTO):
                    if not isinstance(operation, AcceptedAsyncOperationDTO):
                        raise ConflictError("The original suspension has no accepted outcome.")
                    original = await self._lifecycle_result_reader.suspension_original(
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
                        raise ConflictError("The original suspension binding is unavailable.")
                    return replace(original, operation=operation)
                if command.expected_access_revision != facts.access_revision:
                    raise StaleRevisionError()
                target = facts.target
                assert target is not None
                try:
                    suspended = target.suspend()
                except InvalidStateTransitionError as error:
                    raise ConflictError("The target cannot be suspended.") from error
                changed = suspended.status is not target.status
                if changed and facts.access_revision == RevisionValidation.MAX_VALUE:
                    raise ConflictError("The Organization Access revision cannot advance.")
                if changed:
                    cleanup = HumanSuspension(
                        id=HumanSuspensionId(uuid4()),
                        organization_id=facts.organization_id,
                        principal_id=target.id,
                        installation_id=facts.installation_id,
                        authority=identity.authority,
                        subject=identity.subject,
                    )
                else:
                    cleanup = facts.current_suspension
                    if cleanup is None:
                        raise DependencyUnavailableError(
                            "The original suspension obligation is unavailable."
                        )
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
                    raise ConflictError("The original suspension obligation changed its identity.")
                await self._lifecycle_writer.save_suspension(
                    facts=facts,
                    command=command,
                    target=suspended,
                    suspension=cleanup,
                    operation=operation,
                    request_id=request_id,
                )
                completed = await self._operation_idempotency.record_completed_result(
                    operation, replay_kind=OperationReplayKind.ASYNC_JOB
                )
                if (
                    not isinstance(completed, AcceptedAsyncOperationDTO)
                    or completed.operation_id != operation.operation_id
                ):
                    raise ConflictError("Suspension completion changed its operation.")
                result = HumanSuspensionResultDTO(
                    facts.organization_id,
                    target.id,
                    access.actor_principal_id,
                    facts.access_revision + int(changed),
                    OperationId(str(cleanup.id.value)),
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
