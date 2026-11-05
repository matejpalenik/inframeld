from inframeld_backend.shared.application.dtos.artifact_allocation_dto import ArtifactAllocationDTO
from inframeld_backend.shared.application.dtos.artifact_cleanup_job_binding_dto import (
    ArtifactCleanupJobBindingDTO,
)
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.dtos.business_operation_artifact_origin_dto import (
    BusinessOperationArtifactOriginDTO,
)
from inframeld_backend.shared.application.dtos.unadmitted_staging_artifact_origin_dto import (
    UnadmittedStagingArtifactOriginDTO,
)
from inframeld_backend.shared.application.enums.artifact_cleanup_kind import ArtifactCleanupKind
from inframeld_backend.shared.application.errors.artifact_errors import ArtifactReservationError
from inframeld_backend.shared.application.protocols.artifact_attempt_repository import (
    ArtifactAttemptRepository,
)
from inframeld_backend.shared.application.protocols.artifact_capacity_reader import (
    ArtifactCapacityReader,
)
from inframeld_backend.shared.application.protocols.artifact_cleanup_obligation_repository import (
    ArtifactCleanupObligationRepository,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.application.services.artifact_cleanup_admission_service import (
    ArtifactCleanupAdmissionService,
)
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.artifact_cleanup_obligation_id import (
    ArtifactCleanupObligationId,
)
from inframeld_backend.shared.application.value_objects.artifact_id import ArtifactId
from inframeld_backend.shared.application.value_objects.artifact_staging_reservation_id import (
    ArtifactStagingReservationId,
)


class ArtifactAllocationService:
    """Reserve bytes, original obligation, cleanup slot and audit before private effects."""

    def __init__(
        self,
        transaction_manager: TransactionManager,
        artifact_attempt_repository: ArtifactAttemptRepository,
        artifact_cleanup_obligation_repository: ArtifactCleanupObligationRepository,
        artifact_cleanup_admission_service: ArtifactCleanupAdmissionService,
        artifact_capacity_reader: ArtifactCapacityReader,
    ) -> None:
        self._transaction_manager = transaction_manager
        self._artifact_attempt_repository = artifact_attempt_repository
        self._artifact_cleanup_obligation_repository = artifact_cleanup_obligation_repository
        self._artifact_cleanup_admission_service = artifact_cleanup_admission_service
        self._artifact_capacity_reader = artifact_capacity_reader

    async def allocate(
        self,
        *,
        scope: ArtifactScopeDTO,
        artifact_id: ArtifactId,
        attempt_id: ArtifactAttemptId,
        reservation_id: ArtifactStagingReservationId,
        obligation_id: ArtifactCleanupObligationId,
        origin: BusinessOperationArtifactOriginDTO | UnadmittedStagingArtifactOriginDTO,
        limit_bytes: int = 25 * 1024 * 1024,
        transfer_seconds: float = 7200,
    ) -> ArtifactAllocationDTO:
        if isinstance(origin, UnadmittedStagingArtifactOriginDTO) and (
            origin.attempt_id != attempt_id or limit_bytes != 25 * 1024 * 1024
        ):
            raise ArtifactReservationError(
                "Unadmitted source staging reserves its exact full allowance."
            )
        capacity = await self._artifact_capacity_reader.read()
        binding = ArtifactCleanupJobBindingDTO(
            obligation_id, scope, ArtifactCleanupKind.ABANDONED_STAGING, origin
        )
        async with self._transaction_manager.begin():
            reservation = await self._artifact_attempt_repository.reserve(
                scope=scope,
                artifact_id=artifact_id,
                attempt_id=attempt_id,
                reservation_id=reservation_id,
                limit_bytes=limit_bytes,
                transfer_seconds=transfer_seconds,
                capacity=capacity,
            )
            await self._artifact_cleanup_obligation_repository.create_staging(
                binding, targets=(attempt_id,), transfer_deadline=reservation.expires_at
            )
            admission = await self._artifact_cleanup_admission_service.admit(binding)
            result = ArtifactAllocationDTO(reservation, binding, admission.job_id)
        return result
