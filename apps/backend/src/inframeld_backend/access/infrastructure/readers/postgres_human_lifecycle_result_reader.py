from typing import override

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.commands.restore_human_command import RestoreHumanCommand
from inframeld_backend.access.application.commands.suspend_human_command import SuspendHumanCommand
from inframeld_backend.access.application.dtos.human_lifecycle_facts_dto import (
    HumanLifecycleFactsDTO,
)
from inframeld_backend.access.application.dtos.human_restoration_result_dto import (
    HumanRestorationResultDTO,
)
from inframeld_backend.access.application.dtos.human_suspension_result_dto import (
    HumanSuspensionResultDTO,
)
from inframeld_backend.access.application.protocols.human_lifecycle_result_reader import (
    HumanLifecycleResultReader,
)
from inframeld_backend.access.domain.enums.organization_action import OrganizationAction
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.infrastructure.rows.human_lifecycle_operation_result_row import (
    HumanLifecycleOperationResultRow,
)
from inframeld_backend.shared.application.dtos.accepted_async_operation_dto import (
    AcceptedAsyncOperationDTO,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


class PostgresHumanLifecycleResultReader(HumanLifecycleResultReader):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def suspension_original(
        self,
        *,
        facts: HumanLifecycleFactsDTO,
        command: SuspendHumanCommand,
        operation: AcceptedAsyncOperationDTO,
    ) -> HumanSuspensionResultDTO | None:
        row = await self._original(
            facts, command.principal_id, operation.operation_id, OrganizationAction.SUSPEND_USERS
        )
        if row is None or row.cleanup_operation_id is None:
            return None
        return HumanSuspensionResultDTO(
            facts.organization_id,
            command.principal_id,
            facts.actor.id,
            row.access_revision,
            OperationId(str(row.cleanup_operation_id)),
            operation,
        )

    @override
    async def restoration_original(
        self,
        *,
        facts: HumanLifecycleFactsDTO,
        command: RestoreHumanCommand,
        operation: CompletedSynchronousOperationDTO,
    ) -> HumanRestorationResultDTO | None:
        row = await self._original(
            facts, command.principal_id, operation.operation_id, OrganizationAction.RESTORE_USERS
        )
        if row is None or row.credential_version is None:
            return None
        return HumanRestorationResultDTO(
            facts.organization_id,
            command.principal_id,
            facts.actor.id,
            row.access_revision,
            HumanCredentialVersion(row.credential_version),
            operation,
        )

    async def _original(
        self,
        facts: HumanLifecycleFactsDTO,
        principal_id: PrincipalId,
        operation_id: OperationId,
        action: OrganizationAction,
    ) -> HumanLifecycleOperationResultRow | None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Human lifecycle originals require the active caller transaction.")
        return await self._session.scalar(
            select(HumanLifecycleOperationResultRow)
            .where(
                HumanLifecycleOperationResultRow.operation_id == operation_id.value,
                HumanLifecycleOperationResultRow.installation_id == facts.installation_id.value,
                HumanLifecycleOperationResultRow.organization_id == facts.organization_id.value,
                HumanLifecycleOperationResultRow.principal_id == principal_id.value,
                HumanLifecycleOperationResultRow.actor_principal_id == facts.actor.id.value,
                HumanLifecycleOperationResultRow.action_id == action,
            )
            .execution_options(populate_existing=True)
        )
