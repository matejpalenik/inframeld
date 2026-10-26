from typing import override

from sqlalchemy import Nullable, and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from inframeld_backend.access.application.dtos.identity_recovery_admission_dto import (
    IdentityRecoveryAdmissionDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_association_facts_dto import (
    IdentityRecoveryAssociationFactsDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_event_dto import (
    IdentityRecoveryEventDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_session_binding_dto import (
    IdentityRecoverySessionBindingDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_settings_binding_dto import (
    IdentityRecoverySettingsBindingDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_settings_evidence_dto import (
    IdentityRecoverySettingsEvidenceDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.identity_recovery_association_facts_reader import (
    IdentityRecoveryAssociationFactsReader,
)
from inframeld_backend.access.application.value_objects.identity_session_id import IdentitySessionId
from inframeld_backend.access.application.value_objects.identity_settings_flow_id import (
    IdentitySettingsFlowId,
)
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_recovery_flow_id import (
    IdentityRecoveryFlowId,
)
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.infrastructure.resources.postgres_identity_coordinator import (
    PostgresIdentityCoordinator,
)
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
)
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_admission_row import (
    IdentityRecoveryAdmissionRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_session_binding_row import (
    IdentityRecoverySessionBindingRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_settings_binding_row import (
    IdentityRecoverySettingsBindingRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class PostgresIdentityRecoveryAssociationFactsReader(IdentityRecoveryAssociationFactsReader):
    """Read one fresh projection after identity and organization coordination."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        installation_id: InstallationId,
        authority: IdentityAuthority,
    ) -> None:
        self._session = session
        self._installation_id = installation_id
        self._authority = authority

    @override
    async def read(
        self, evidence: IdentityRecoverySettingsEvidenceDTO
    ) -> IdentityRecoveryAssociationFactsDTO:
        if evidence.identity.authority != self._authority:
            raise ConflictError("The notification provider does not match configuration.")
        await PostgresIdentityCoordinator(self._session).acquire(
            installation_id=self._installation_id, identity=evidence.identity
        )
        await self._session.scalar(
            select(OrganizationRow.id)
            .join(HumanIdentityLinkRow, HumanIdentityLinkRow.organization_id == OrganizationRow.id)
            .where(
                HumanIdentityLinkRow.authority == evidence.identity.authority.value,
                HumanIdentityLinkRow.subject == evidence.identity.subject.value,
            )
            .with_for_update(of=OrganizationRow)
            .execution_options(autoflush=False)
        )
        source = aliased(IdentityRecoveryAdmissionRow)
        session_admission = aliased(IdentityRecoveryAdmissionRow)
        settings_admission = aliased(IdentityRecoveryAdmissionRow)
        source_id = evidence.source_recovery_flow_id
        result = await self._session.execute(
            select(
                InstallationIdentityRow.installation_id,
                Nullable(source),
                Nullable(IdentityRecoverySessionBindingRow),
                Nullable(session_admission),
                Nullable(IdentityRecoverySettingsBindingRow),
                Nullable(settings_admission),
                Nullable(HumanCredentialVersionRow.version),
            )
            .select_from(InstallationIdentityRow)
            .outerjoin(
                source,
                and_(
                    source.installation_id == InstallationIdentityRow.installation_id,
                    source.authority == self._authority.value,
                    source.flow_id == (None if source_id is None else source_id.value),
                ),
            )
            .outerjoin(
                IdentityRecoverySessionBindingRow,
                and_(
                    IdentityRecoverySessionBindingRow.installation_id
                    == InstallationIdentityRow.installation_id,
                    IdentityRecoverySessionBindingRow.authority == self._authority.value,
                    IdentityRecoverySessionBindingRow.session_id == evidence.session_id.value,
                ),
            )
            .outerjoin(
                session_admission,
                and_(
                    session_admission.installation_id == InstallationIdentityRow.installation_id,
                    session_admission.authority == self._authority.value,
                    session_admission.operation_id
                    == IdentityRecoverySessionBindingRow.operation_id,
                ),
            )
            .outerjoin(
                IdentityRecoverySettingsBindingRow,
                and_(
                    IdentityRecoverySettingsBindingRow.installation_id
                    == InstallationIdentityRow.installation_id,
                    IdentityRecoverySettingsBindingRow.authority == self._authority.value,
                    IdentityRecoverySettingsBindingRow.settings_flow_id
                    == evidence.settings_flow_id.value,
                ),
            )
            .outerjoin(
                settings_admission,
                and_(
                    settings_admission.installation_id == InstallationIdentityRow.installation_id,
                    settings_admission.authority == self._authority.value,
                    settings_admission.operation_id
                    == IdentityRecoverySettingsBindingRow.operation_id,
                ),
            )
            .outerjoin(
                HumanCredentialVersionRow,
                and_(
                    HumanCredentialVersionRow.installation_id
                    == InstallationIdentityRow.installation_id,
                    HumanCredentialVersionRow.authority == self._authority.value,
                    HumanCredentialVersionRow.subject == evidence.identity.subject.value,
                ),
            )
            .where(InstallationIdentityRow.singleton_key == 1)
            .execution_options(autoflush=False, populate_existing=True)
        )
        row = result.tuples().one_or_none()
        if row is None or row[0] != self._installation_id.value:
            raise DependencyUnavailableError()
        _, source_row, session_row, session_recovery, settings_row, settings_recovery, version = row
        return IdentityRecoveryAssociationFactsDTO(
            source_admission=self._to_admission(source_row),
            session_binding=None
            if session_row is None
            else IdentityRecoverySessionBindingDTO(
                VerifiedHumanIdentityDTO(
                    IdentityAuthority(session_row.authority), IdentitySubject(session_row.subject)
                ),
                IdentitySessionId(session_row.session_id),
                OperationId(session_row.operation_id),
            ),
            session_admission=self._to_admission(session_recovery),
            settings_binding=None
            if settings_row is None
            else IdentityRecoverySettingsBindingDTO(
                VerifiedHumanIdentityDTO(
                    IdentityAuthority(settings_row.authority), IdentitySubject(settings_row.subject)
                ),
                IdentitySettingsFlowId(settings_row.settings_flow_id),
                IdentitySessionId(settings_row.session_id),
                OperationId(settings_row.operation_id),
                None
                if settings_row.source_recovery_flow_id is None
                else IdentityRecoveryFlowId(settings_row.source_recovery_flow_id),
            ),
            settings_admission=self._to_admission(settings_recovery),
            current_version=None if version is None else HumanCredentialVersion(version),
        )

    @staticmethod
    def _to_admission(
        row: IdentityRecoveryAdmissionRow | None,
    ) -> IdentityRecoveryAdmissionDTO | None:
        if row is None:
            return None
        return IdentityRecoveryAdmissionDTO(
            IdentityRecoveryEventDTO(
                IdentityRecoveryFlowId(row.flow_id),
                VerifiedHumanIdentityDTO(
                    IdentityAuthority(row.authority), IdentitySubject(row.subject)
                ),
                row.event_kind,
            ),
            OperationId(row.operation_id),
        )
