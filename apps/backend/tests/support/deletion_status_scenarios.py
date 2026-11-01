"""Seed native reservations and private read history without proving deletion effects."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import DateTime, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.browser_session_authentication_dto import (
    BrowserSessionAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.deletion_status_authorization_dto import (
    DeletionStatusAuthorizationDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.project_action_authorization_dto import (
    ProjectActionAuthorizationDTO,
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
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
)
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
)
from inframeld_backend.shared.application.dtos.operation_admission_context_dto import (
    OperationAdmissionContextDTO,
)
from inframeld_backend.shared.application.dtos.operation_reservation_request_dto import (
    OperationReservationRequestDTO,
)
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.application.value_objects.deletion_status_retention_profile import (
    DeletionStatusRetentionProfile,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)
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
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)
from tests.support.access_scenarios import MockAccessScenarios


@dataclass(frozen=True, slots=True)
class DeletionStatusSeedDTO:
    """Keep trusted fixture attribution separate from native reservation fields."""

    access: AccessContextDTO
    request: OperationReservationRequestDTO
    reservation: NewOperationReservationDTO
    request_id: RequestId
    installation_id: InstallationId
    identity: VerifiedHumanIdentityDTO

    def authorization(self) -> DeletionStatusAuthorizationDTO:
        return DeletionStatusAuthorizationDTO(
            self.reservation.operation_id,
            self.installation_id,
            self.request.organization_id,
            self.request.principal_id,
        )

    def oauth_access(self) -> AccessContextDTO:
        return AccessContextDTO(
            self.access.actor_principal_id,
            HumanOAuthCredentialBindingDTO(
                self.identity, self.installation_id, HumanCredentialVersion(1)
            ),
        )


class MockDeletionStatusScenarios:
    """Create fixture evidence for reader qualification, never a deletion producer."""

    @staticmethod
    async def seed_native_request(
        session: AsyncSession,
        *,
        with_oauth_generation: bool = True,
        identity: VerifiedHumanIdentityDTO | None = None,
    ) -> DeletionStatusSeedDTO:
        actor = await MockAccessScenarios.seed_project_authorization(
            session, is_project_member=True, has_action_grant=False
        )
        installation = InstallationId(
            (await session.scalars(select(InstallationIdentityRow.installation_id))).one()
        )
        if identity is None:
            identity = VerifiedHumanIdentityDTO(
                IdentityAuthority("kratos:deletion-status-test"), IdentitySubject(str(uuid4()))
            )
        session.add(
            HumanIdentityLinkRow(
                authority=identity.authority.value,
                subject=identity.subject.value,
                organization_id=actor.organization_id.value,
                principal_id=actor.principal_id.value,
                principal_kind=PrincipalKind.HUMAN,
            )
        )
        if with_oauth_generation:
            session.add(
                HumanCredentialVersionRow(
                    installation_id=installation.value,
                    authority=identity.authority.value,
                    subject=identity.subject.value,
                    version=1,
                )
            )
        await session.flush()
        access = AccessContextDTO(actor.principal_id, BrowserSessionAuthenticationDTO(identity))
        request = OperationReservationRequestDTO(
            principal_id=actor.principal_id,
            organization_id=actor.organization_id,
            project_id=actor.project_id,
            method="DELETE",
            requested_route="/v1/projects/{project_id}",
            key=IdempotencyKey(str(uuid4())),
            fingerprint=b"F" * 32,
            lookup_authority=OperationLookupAuthority(
                OperationLookupAuthorityFamily.PROJECT_ACTION_USE, ActionId("delete-project")
            ),
        )
        # This exercises native reservation, not Delete authorization or admission.
        reserved = await IdempotencyService(
            PostgresOperationReservationWriter(session)
        ).find_or_reserve(
            context=OperationAdmissionContextDTO(
                request.method, request.requested_route, request.key
            ),
            access=access,
            authorization=ProjectActionAuthorizationDTO(actor.organization_id, actor.project_id),
            fingerprint=RequestFingerprint(request.fingerprint),
            expected_replay_kind=OperationReplayKind.ASYNC_JOB,
            lookup_authority=request.lookup_authority,
        )
        assert isinstance(reserved, NewOperationReservationDTO)
        return DeletionStatusSeedDTO(
            access, request, reserved, RequestId(uuid4()), installation, identity
        )

    @staticmethod
    async def seed_private_binding(
        session: AsyncSession,
        *,
        days: int = 30,
        with_oauth_generation: bool = True,
        identity: VerifiedHumanIdentityDTO | None = None,
    ) -> DeletionStatusSeedDTO:
        """Supply retained correlation independently of the writer being qualified."""
        seed = await MockDeletionStatusScenarios.seed_native_request(
            session, with_oauth_generation=with_oauth_generation, identity=identity
        )
        request = seed.request
        assert request.project_id is not None
        assert request.lookup_authority is not None
        profile = DeletionStatusRetentionProfile(days)
        session.add(
            DeletionStatusBindingRow(
                operation_id=seed.reservation.operation_id.value,
                request_id=seed.request_id.value,
                installation_id=seed.installation_id.value,
                organization_id=request.organization_id.value,
                project_id=request.project_id.value,
                initiator_principal_id=request.principal_id.value,
                method=request.method,
                requested_route=request.requested_route,
                request_key=request.key.value,
                request_fingerprint=request.fingerprint,
                authority_family=request.lookup_authority.family.value,
                action_id=request.lookup_authority.action_id.value,
                retention_days=profile.days,
                retention_policy_version=profile.policy_version,
            )
        )
        await session.flush()
        return seed

    @staticmethod
    async def seed_private_observation(
        session: AsyncSession,
        *,
        days: int = 30,
        age_days: int = 0,
        active: bool = False,
        with_oauth_generation: bool = True,
        identity: VerifiedHumanIdentityDTO | None = None,
    ) -> DeletionStatusSeedDTO:
        """Populate only read/auth/retention fixtures, without authentic producer proof."""
        seed = await MockDeletionStatusScenarios.seed_private_binding(
            session, days=days, with_oauth_generation=with_oauth_generation, identity=identity
        )
        now = (
            await session.execute(select(func.clock_timestamp(type_=DateTime(timezone=True))))
        ).scalar_one()
        assert isinstance(now, datetime)
        started = now - timedelta(days=age_days)
        await session.execute(
            update(DeletionStatusBindingRow)
            .where(DeletionStatusBindingRow.operation_id == seed.reservation.operation_id.value)
            .values(recorded_at=started - timedelta(seconds=1))
        )
        request = seed.request
        assert request.project_id is not None
        session.add(
            DeletionStatusObservationRow(
                operation_id=seed.reservation.operation_id.value,
                owner_revision=1,
                job_status=JobStatus.FAILED.value if active else JobStatus.SUCCEEDED.value,
                admission_confirmed=True,
                access_blocked=True,
                application_shutdown_complete=True,
                physical_cleanup_complete=None if active else True,
                retention_started_at=None if active else started,
                expires_at=None if active else started + timedelta(days=days),
                unfinished_obligation_id=uuid4() if active else None,
                unfinished_operation_id=seed.reservation.operation_id.value if active else None,
                unfinished_installation_id=seed.installation_id.value if active else None,
                unfinished_organization_id=request.organization_id.value if active else None,
                unfinished_project_id=request.project_id.value if active else None,
                unfinished_initiator_principal_id=request.principal_id.value if active else None,
                unfinished_observed_at=now if active else None,
                unfinished_source_revision=1 if active else None,
            )
        )
        await session.flush()
        return seed
