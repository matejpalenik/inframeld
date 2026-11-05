from dataclasses import replace
from typing import override

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_action_authorization_request_dto import (
    ProjectActionAuthorizationRequestDTO,
)
from inframeld_backend.access.application.protocols.project_budget_authorizer import (
    ProjectBudgetAuthorizer,
)
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.commands.change_project_spending_policy_command import (
    ChangeProjectSpendingPolicyCommand,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import (
    IdempotencyContextDTO,
)
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
)
from inframeld_backend.shared.application.dtos.project_spending_policy_dto import (
    ProjectSpendingPolicyDTO,
)
from inframeld_backend.shared.application.dtos.project_spending_policy_result_dto import (
    ProjectSpendingPolicyResultDTO,
)
from inframeld_backend.shared.application.dtos.spending_projection_dto import SpendingProjectionDTO
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.protocols.operation_idempotency import (
    OperationIdempotency,
)
from inframeld_backend.shared.application.protocols.project_spending_policy_manager import (
    ProjectSpendingPolicyManager,
)
from inframeld_backend.shared.application.protocols.spending_ledger_reader import (
    SpendingLedgerReader,
)
from inframeld_backend.shared.application.protocols.spending_ledger_writer import (
    SpendingLedgerWriter,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.application.services.project_spending_policy_fingerprint_service import (
    ProjectSpendingPolicyFingerprintService,
)
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)
from inframeld_backend.shared.application.value_objects.spending_period import SpendingPeriod


class ProjectSpendingPolicyService(ProjectSpendingPolicyManager):
    """Coordinate human policy mutation without changing charges, holds or jobs."""

    def __init__(
        self,
        *,
        transaction_manager: TransactionManager,
        project_budget_authorizer: ProjectBudgetAuthorizer,
        spending_ledger_reader: SpendingLedgerReader,
        spending_ledger_writer: SpendingLedgerWriter,
        operation_idempotency: OperationIdempotency,
        spending_policy_fingerprint_service: ProjectSpendingPolicyFingerprintService,
    ) -> None:
        self._transaction_manager = transaction_manager
        self._project_budget_authorizer = project_budget_authorizer
        self._spending_ledger_reader = spending_ledger_reader
        self._spending_ledger_writer = spending_ledger_writer
        self._operation_idempotency = operation_idempotency
        self._spending_policy_fingerprint_service = spending_policy_fingerprint_service

    @override
    async def change_limit(
        self,
        *,
        access: AccessContextDTO,
        command: ChangeProjectSpendingPolicyCommand,
        context: IdempotencyContextDTO,
    ) -> ProjectSpendingPolicyResultDTO:
        fingerprint = self._spending_policy_fingerprint_service.for_change(command)
        async with self._transaction_manager.begin():
            authorization = await self._project_budget_authorizer.require_authorization(
                access=access,
                request=ProjectActionAuthorizationRequestDTO(
                    command.project_id, ActionId(ProjectAction.MANAGE_BUDGET.value)
                ),
            )
            if authorization.project_id != command.project_id:
                raise AccessDeniedError()
            operation = await self._operation_idempotency.reserve_or_recover(
                context=context,
                access=access,
                authorization=authorization,
                fingerprint=fingerprint,
                expected_replay_kind=OperationReplayKind.SAFE_RESULT,
                lookup_authority=OperationLookupAuthority(
                    OperationLookupAuthorityFamily.PROJECT_ACTION_USE,
                    ActionId(ProjectAction.MANAGE_BUDGET.value),
                ),
            )
            if isinstance(operation, CompletedSynchronousOperationDTO):
                result = await self._spending_ledger_reader.policy_result(
                    organization_id=authorization.organization_id,
                    project_id=command.project_id,
                    actor_id=access.actor_principal_id,
                    completion=operation,
                )
                self._require_scope(
                    result.policy, authorization.organization_id, command.project_id
                )
                return result
            if not isinstance(operation, NewOperationReservationDTO):
                raise ConflictError("Budget policy requires a synchronous safe result.")
            await self._spending_ledger_writer.ensure_project_account(
                organization_id=authorization.organization_id, project_id=command.project_id
            )
            policy = await self._spending_ledger_reader.lock_project_policy(
                organization_id=authorization.organization_id, project_id=command.project_id
            )
            self._require_scope(policy, authorization.organization_id, command.project_id)
            if policy.revision != command.expected_policy_revision:
                raise StaleRevisionError()
            changed = policy.monthly_limit != command.monthly_limit
            if changed:
                policy = replace(
                    policy, revision=policy.revision + 1, monthly_limit=command.monthly_limit
                )
                await self._spending_ledger_writer.change_policy(
                    policy=policy,
                    expected_revision=command.expected_policy_revision,
                    actor_id=access.actor_principal_id,
                    operation_id=operation.operation_id,
                )
            await self._spending_ledger_writer.save_policy_result(
                policy=policy,
                actor_id=access.actor_principal_id,
                operation_id=operation.operation_id,
                changed=changed,
            )
            completion = await self._operation_idempotency.record_completed_result(
                operation, replay_kind=OperationReplayKind.SAFE_RESULT
            )
            if not isinstance(completion, CompletedSynchronousOperationDTO):
                raise ConflictError("Budget policy completion requires a synchronous safe result.")
            return ProjectSpendingPolicyResultDTO(policy, completion, changed)

    @override
    async def inspect(
        self, *, access: AccessContextDTO, project_id: ProjectId, period: SpendingPeriod
    ) -> SpendingProjectionDTO:
        async with self._transaction_manager.begin():
            authorization = await self._project_budget_authorizer.require_authorization(
                access=access,
                request=ProjectActionAuthorizationRequestDTO(
                    project_id, ActionId(ProjectAction.INSPECT_BUDGET.value)
                ),
            )
            if authorization.project_id != project_id:
                raise AccessDeniedError()
            projection = await self._spending_ledger_reader.project_projection(
                organization_id=authorization.organization_id, project_id=project_id, period=period
            )
            self._require_scope(projection.policy, authorization.organization_id, project_id)
            if projection.period != period:
                raise RuntimeError("Accounting projection changed its period scope.")
            return projection

    @staticmethod
    def _require_scope(
        policy: ProjectSpendingPolicyDTO, organization_id: OrganizationId, project_id: ProjectId
    ) -> None:
        if (policy.organization_id, policy.project_id) != (organization_id, project_id):
            raise RuntimeError("Accounting policy changed its scope.")
