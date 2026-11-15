from datetime import datetime

from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.dtos.artifact_staging_reservation_dto import (
    ArtifactStagingReservationDTO,
)
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.artifact_content_digest import (
    ArtifactContentDigest,
)
from inframeld_backend.shared.application.value_objects.artifact_id import ArtifactId
from inframeld_backend.shared.application.value_objects.artifact_staging_reservation_id import (
    ArtifactStagingReservationId,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.rows.artifact_attempt_row import ArtifactAttemptRow
from inframeld_backend.shared.infrastructure.rows.artifact_staging_reservation_row import (
    ArtifactStagingReservationRow,
)


class PostgresArtifactAttemptMapper:
    @staticmethod
    def reservation(
        attempt: ArtifactAttemptRow,
        reservation: ArtifactStagingReservationRow,
        observed_at: datetime,
    ) -> ArtifactStagingReservationDTO:
        return ArtifactStagingReservationDTO(
            reservation_id=ArtifactStagingReservationId(reservation.id),
            artifact_id=ArtifactId(attempt.artifact_id),
            attempt_id=ArtifactAttemptId(attempt.id),
            scope=ArtifactScopeDTO(
                InstallationId(attempt.installation_id),
                OrganizationId(attempt.organization_id),
                ProjectId(attempt.project_id),
            ),
            limit_bytes=reservation.limit_bytes,
            expires_at=reservation.expires_at,
            observed_at=observed_at,
            released=reservation.released,
            retired=attempt.retired,
            length=attempt.length,
            digest=ArtifactContentDigest(attempt.digest) if attempt.digest is not None else None,
            put_pending=attempt.put_pending,
            put_confirmed=attempt.put_confirmed,
            published=attempt.published,
            staging_removed=reservation.staging_removed,
        )
