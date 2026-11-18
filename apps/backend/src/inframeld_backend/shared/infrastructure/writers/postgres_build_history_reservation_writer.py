from typing import override

from sqlalchemy import String, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.pipelines.domain.value_objects.pipeline_id import PipelineId
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.errors.retained_history_errors import (
    RetainedHistoryCapacityError,
)
from inframeld_backend.shared.application.protocols.build_history_reservation_writer import (
    BuildHistoryReservationWriter,
)
from inframeld_backend.shared.application.protocols.retained_history_safety_headroom import (
    RetainedHistorySafetyHeadroom,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)
from inframeld_backend.shared.infrastructure.rows.retained_history_capacity_row import (
    RetainedHistoryCapacityRow,
)
from inframeld_backend.shared.infrastructure.rows.retained_history_reservation_row import (
    RetainedHistoryReservationRow,
)

# The bounded job payload and checkpoint are at most 64 KiB each. Allow room
# for the capture, up to three attempts, completion report, audit and original.
# This is a logical charge. Independently owned storage gates protect the host.
_BUILD_HISTORY_BYTES = 1 << 20


class PostgresBuildHistoryReservationWriter(BuildHistoryReservationWriter):
    """Reserve one bounded Build envelope under the installation budget turn."""

    def __init__(
        self, session: AsyncSession, *, safety_headroom: RetainedHistorySafetyHeadroom
    ) -> None:
        self._session = session
        self._safety_headroom = safety_headroom

    @override
    async def reserve_build(
        self, *, scope: ArtifactScopeDTO, operation_id: OperationId, pipeline_id: PipelineId
    ) -> None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Build history reservation requires an active transaction.")
        isolation = await self._session.scalar(
            select(func.current_setting("transaction_isolation", type_=String()))
        )
        if isolation != "read committed":
            raise RuntimeError("Build history reservation requires READ COMMITTED.")

        # The owning Build transaction reserves the original before taking the ledger turn.
        original = await self._session.scalar(
            select(IdempotencyReservationRow.operation_id)
            .where(
                IdempotencyReservationRow.operation_id == operation_id.value,
                IdempotencyReservationRow.organization_id == scope.organization_id.value,
                IdempotencyReservationRow.project_id == scope.project_id.value,
                IdempotencyReservationRow.method == HttpMethod.POST.value,
                IdempotencyReservationRow.requested_route
                == f"/internal/projects/{scope.project_id.value}/pipelines/{pipeline_id.value}/builds",
                IdempotencyReservationRow.lookup_authority_family.is_(None),
                IdempotencyReservationRow.lookup_action_id.is_(None),
                IdempotencyReservationRow.state == OperationReservationState.IN_PROGRESS,
                IdempotencyReservationRow.replay_kind.is_(None),
                IdempotencyReservationRow.expires_at.is_(None),
                exists().where(
                    InstallationIdentityRow.singleton_key == 1,
                    InstallationIdentityRow.installation_id == scope.installation_id.value,
                ),
            )
            .with_for_update(of=IdempotencyReservationRow)
        )
        if original is None:
            raise ConflictError("Build history requires its exact active original reservation.")

        capacity = await self._session.get(
            RetainedHistoryCapacityRow, 1, with_for_update=True, populate_existing=True
        )
        if capacity is None:
            raise DependencyUnavailableError("The retained-history budget is unavailable.")
        prior = await self._session.get(
            RetainedHistoryReservationRow, original, populate_existing=True
        )
        if prior is not None:
            if (prior.installation_id, prior.organization_id, prior.project_id) != (
                scope.installation_id.value,
                scope.organization_id.value,
                scope.project_id.value,
            ):
                raise ConflictError("The original Build history scope does not match.")
            return

        await self._safety_headroom.require_headroom(installation_id=scope.installation_id)
        updated = capacity.reserved_bytes + _BUILD_HISTORY_BYTES
        if updated > capacity.ordinary_limit_bytes:
            raise RetainedHistoryCapacityError("The ordinary retained-history budget is full.")

        capacity.reserved_bytes = updated
        self._session.add(
            RetainedHistoryReservationRow(
                operation_id=original,
                installation_id=scope.installation_id.value,
                organization_id=scope.organization_id.value,
                project_id=scope.project_id.value,
                reserved_bytes=_BUILD_HISTORY_BYTES,
            )
        )
        await self._session.flush()
