from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.protocols.project_grant_change_facts_reader import (
    ProjectGrantChangeFactsReader,
)
from inframeld_backend.access.application.protocols.project_grant_change_writer import (
    ProjectGrantChangeWriter,
)
from inframeld_backend.access.domain.policies.project_grant_delegation_policy import (
    ProjectGrantDelegationPolicy,
)
from inframeld_backend.access.domain.policies.project_visibility_policy import (
    ProjectVisibilityPolicy,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.dtos.operation_reservation_request_dto import (
    OperationReservationRequestDTO,
)
from inframeld_backend.shared.application.dtos.operation_reservation_result_dto import (
    OperationReservationResultDTO,
)
from inframeld_backend.shared.application.dtos.project_operation_admission_request_dto import (
    ProjectOperationAdmissionRequestDTO,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    IdempotencyInProgressError,
    ResourceNotFoundError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.protocols.operation_reservation_writer import (
    OperationReservationWriter,
)


class ProjectGrantChangeService:
    """Authorize and save one project grant change in a caller-owned transaction."""

    def __init__(
        self,
        facts_reader: ProjectGrantChangeFactsReader,
        reservations: OperationReservationWriter,
        changes: ProjectGrantChangeWriter,
    ) -> None:
        self._facts_reader = facts_reader
        self._reservations = reservations
        self._changes = changes

    async def assign_use_only(
        self,
        *,
        access: AccessContextDTO,
        request: ProjectOperationAdmissionRequestDTO,
        recipient_principal_id: PrincipalId,
        action_id: ActionId,
        expected_access_revision: int,
    ) -> OperationReservationResultDTO:
        facts = await self._facts_reader.read_for_change(
            access=access,
            project_id=request.project_id,
            recipient_principal_id=recipient_principal_id,
            action_id=action_id,
        )

        if facts is None or not ProjectVisibilityPolicy.may_view_project(
            principal_status=facts.actor.status,
            project_status=facts.project_status,
            is_project_member=facts.actor_is_project_member,
        ):
            raise ResourceNotFoundError()

        if not ProjectGrantDelegationPolicy.may_delegate_project_action(
            actor=facts.actor,
            actor_is_project_member=facts.actor_is_project_member,
            actor_can_grant_action=facts.actor_can_grant_action,
        ):
            raise AccessDeniedError()

        if facts.recipient is None:
            raise ResourceNotFoundError()

        if not ProjectGrantDelegationPolicy.may_assign_use_only_to_human(
            actor=facts.actor,
            recipient=facts.recipient,
            actor_is_project_member=facts.actor_is_project_member,
            recipient_is_project_member=facts.recipient_is_project_member,
            actor_can_grant_action=facts.actor_can_grant_action,
        ):
            raise AccessDeniedError()

        reservation = await self._reservations.reserve(
            OperationReservationRequestDTO(
                principal_id=access.actor_principal_id,
                organization_id=facts.actor.organization_id,
                project_id=request.project_id,
                method=request.method,
                requested_route=request.requested_route,
                key=request.key,
                fingerprint=request.fingerprint,
            )
        )

        if not reservation.created:
            if reservation.state is OperationReservationState.IN_PROGRESS:
                raise IdempotencyInProgressError(
                    operation_id=reservation.operation_id,
                    retry_after_seconds=3,
                )
            if reservation.state is OperationReservationState.RECOVERY_REQUIRED:
                return reservation
            if (
                reservation.state is OperationReservationState.REPLAYABLE
                and reservation.replay_kind is OperationReplayKind.SAFE_RESULT
            ):
                return reservation
            raise ConflictError("The saved operation has an unexpected replay outcome.")

        # An old expected revision must not block a replay, so check it only
        # after determining that this reservation is new.
        if facts.project_access_revision != expected_access_revision:
            raise StaleRevisionError

        await self._changes.create_use_only(
            organization_id=facts.actor.organization_id,
            project_id=request.project_id,
            actor_principal_id=access.actor_principal_id,
            recipient_principal_id=recipient_principal_id,
            action_id=action_id,
            expected_access_revision=expected_access_revision,
            operation_id=reservation.operation_id,
        )
        expires_at = await self._reservations.mark_replayable(
            reservation.operation_id,
            OperationReplayKind.SAFE_RESULT,
        )

        return OperationReservationResultDTO(
            operation_id=reservation.operation_id,
            created=True,
            state=OperationReservationState.REPLAYABLE,
            replay_kind=OperationReplayKind.SAFE_RESULT,
            expires_at=expires_at,
        )
