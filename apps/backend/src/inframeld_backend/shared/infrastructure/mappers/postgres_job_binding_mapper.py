from inframeld_backend.access.application.dtos.admitted_work_authority_dto import (
    AdmittedWorkAuthorityDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.artifact_cleanup_job_binding_dto import (
    ArtifactCleanupJobBindingDTO,
)
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.dtos.business_operation_artifact_origin_dto import (
    BusinessOperationArtifactOriginDTO,
)
from inframeld_backend.shared.application.dtos.product_job_binding_dto import ProductJobBindingDTO
from inframeld_backend.shared.application.dtos.project_deletion_job_binding_dto import (
    ProjectDeletionJobBindingDTO,
)
from inframeld_backend.shared.application.dtos.unadmitted_staging_artifact_origin_dto import (
    UnadmittedStagingArtifactOriginDTO,
)
from inframeld_backend.shared.application.enums.artifact_cleanup_kind import ArtifactCleanupKind
from inframeld_backend.shared.application.errors.artifact_errors import ArtifactReservationError
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.artifact_cleanup_obligation_id import (
    ArtifactCleanupObligationId,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.rows.artifact_cleanup_obligation_row import (
    ArtifactCleanupObligationRow,
)
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow
from inframeld_backend.shared.infrastructure.rows.project_deletion_obligation_row import (
    ProjectDeletionObligationRow,
)


class PostgresJobBindingMapper:
    @staticmethod
    def cleanup(row: ArtifactCleanupObligationRow) -> ArtifactCleanupJobBindingDTO:
        origin: BusinessOperationArtifactOriginDTO | UnadmittedStagingArtifactOriginDTO
        if (
            row.origin_kind == "business"
            and row.origin_operation_id is not None
            and row.origin_attempt_id is None
        ):
            origin = BusinessOperationArtifactOriginDTO(
                OperationId(row.origin_operation_id), RequestId(row.request_id)
            )
        elif (
            row.origin_kind == "unadmitted_staging"
            and row.origin_attempt_id is not None
            and row.origin_operation_id is None
        ):
            origin = UnadmittedStagingArtifactOriginDTO(
                ArtifactAttemptId(row.origin_attempt_id), RequestId(row.request_id)
            )
        else:
            raise ArtifactReservationError("The original cleanup attribution is incomplete.")
        return ArtifactCleanupJobBindingDTO(
            ArtifactCleanupObligationId(row.id),
            ArtifactScopeDTO(
                InstallationId(row.installation_id),
                OrganizationId(row.organization_id),
                ProjectId(row.project_id),
            ),
            ArtifactCleanupKind(row.kind),
            origin,
        )

    @staticmethod
    def product(row: DurableJobRow) -> ProductJobBindingDTO:
        if (
            row.binding_kind != "product"
            or row.deletion_obligation_id is not None
            or row.cleanup_obligation_id is not None
            or row.operation_id is None
            or row.principal_id is None
            or row.principal_kind is None
            or row.action_id is None
        ):
            raise ArtifactReservationError("The original product job binding is incomplete.")
        human = None
        if (
            row.human_authority is not None
            or row.human_subject is not None
            or row.human_version is not None
        ):
            if (
                row.human_authority is None
                or row.human_subject is None
                or row.human_version is None
            ):
                raise ArtifactReservationError(
                    "The original human security generation is incomplete."
                )
            human = HumanOAuthCredentialBindingDTO(
                VerifiedHumanIdentityDTO(
                    IdentityAuthority(row.human_authority), IdentitySubject(row.human_subject)
                ),
                InstallationId(row.installation_id),
                HumanCredentialVersion(row.human_version),
            )
        authority = AdmittedWorkAuthorityDTO(
            principal_id=PrincipalId(row.principal_id),
            principal_kind=PrincipalKind(row.principal_kind),
            installation_id=InstallationId(row.installation_id),
            organization_id=OrganizationId(row.organization_id),
            project_id=ProjectId(row.project_id),
            action_id=ActionId(row.action_id),
            human_binding=human,
        )
        return ProductJobBindingDTO(
            OperationId(row.operation_id), RequestId(row.request_id), authority
        )

    @staticmethod
    def project_deletion(row: ProjectDeletionObligationRow) -> ProjectDeletionJobBindingDTO:
        return ProjectDeletionJobBindingDTO(
            row.id,
            OperationId(row.operation_id),
            RequestId(row.request_id),
            InstallationId(row.installation_id),
            row.organization_id,
            row.project_id,
            row.initiator_principal_id,
            IdempotencyKey(row.request_key),
            RequestFingerprint(row.request_fingerprint),
            row.before_access_revision,
            row.access_revision,
        )
