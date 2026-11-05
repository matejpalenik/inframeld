from datetime import datetime

from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.deletion_status_binding_dto import (
    DeletionStatusBindingDTO,
)
from inframeld_backend.shared.application.dtos.deletion_status_obligation_provenance_dto import (
    DeletionStatusObligationProvenanceDTO,
)
from inframeld_backend.shared.application.dtos.deletion_status_observation_dto import (
    DeletionStatusObservationDTO,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.enums.job_status import JobStatus
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.rows.deletion_status_binding_row import (
    DeletionStatusBindingRow,
)
from inframeld_backend.shared.infrastructure.rows.deletion_status_observation_row import (
    DeletionStatusObservationRow,
)


class PostgresDeletionStatusMapper:
    """Decode retained representations without establishing source proof or authority."""

    @staticmethod
    def to_binding(row: DeletionStatusBindingRow) -> DeletionStatusBindingDTO:
        if row.method not in ("POST", "PUT", "PATCH", "DELETE"):
            raise ValueError("The retained request method is not supported.")
        method = HttpMethod(row.method)
        return DeletionStatusBindingDTO(
            operation_id=OperationId(row.operation_id),
            request_id=RequestId(row.request_id),
            installation_id=InstallationId(row.installation_id),
            organization_id=OrganizationId(row.organization_id),
            project_id=ProjectId(row.project_id),
            initiator_principal_id=PrincipalId(row.initiator_principal_id),
            method=method,
            requested_route=row.requested_route,
            key=IdempotencyKey(row.request_key),
            fingerprint=RequestFingerprint(row.request_fingerprint),
            authority_family=OperationLookupAuthorityFamily(row.authority_family),
            action_id=ActionId(row.action_id),
            recorded_at=row.recorded_at,
            retention_days=row.retention_days,
            retention_policy_version=row.retention_policy_version,
        )

    @staticmethod
    def to_observation(
        binding: DeletionStatusBindingRow,
        owner: DeletionStatusObservationRow | None,
        observed_at: datetime,
    ) -> DeletionStatusObservationDTO:
        retained = PostgresDeletionStatusMapper.to_binding(binding)
        if owner is None:
            return DeletionStatusObservationDTO(retained, observed_at)

        return DeletionStatusObservationDTO(
            binding=retained,
            observed_at=observed_at,
            owner_revision=owner.owner_revision,
            owner_observed_at=owner.owner_observed_at,
            job_status=JobStatus(owner.job_status) if owner.job_status is not None else None,
            admission_confirmed=owner.admission_confirmed,
            access_blocked=owner.access_blocked,
            application_shutdown_complete=owner.application_shutdown_complete,
            physical_cleanup_complete=owner.physical_cleanup_complete,
            unfinished_obligation=PostgresDeletionStatusMapper._to_unfinished_obligation(owner),
            retention_started_at=owner.retention_started_at,
            expires_at=owner.expires_at,
        )

    @staticmethod
    def _to_unfinished_obligation(
        row: DeletionStatusObservationRow,
    ) -> DeletionStatusObligationProvenanceDTO | None:
        obligation_id = row.unfinished_obligation_id
        operation_id = row.unfinished_operation_id
        installation_id = row.unfinished_installation_id
        organization_id = row.unfinished_organization_id
        project_id = row.unfinished_project_id
        initiator = row.unfinished_initiator_principal_id
        observed_at = row.unfinished_observed_at
        revision = row.unfinished_source_revision
        if all(
            value is None
            for value in (
                obligation_id,
                operation_id,
                installation_id,
                organization_id,
                project_id,
                initiator,
                observed_at,
                revision,
            )
        ):
            return None
        if (
            obligation_id is None
            or operation_id is None
            or installation_id is None
            or organization_id is None
            or project_id is None
            or initiator is None
            or observed_at is None
            or revision is None
        ):
            raise ValueError("The retained unfinished-obligation metadata is incomplete.")

        return DeletionStatusObligationProvenanceDTO(
            obligation_id=obligation_id,
            operation_id=OperationId(operation_id),
            installation_id=InstallationId(installation_id),
            organization_id=OrganizationId(organization_id),
            project_id=ProjectId(project_id),
            initiator_principal_id=PrincipalId(initiator),
            observed_at=observed_at,
            source_revision=revision,
        )
