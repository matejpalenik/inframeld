import asyncio
from typing import override
from uuid import uuid4

from sqlalchemy import literal, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.identity_recovery_admission_dto import (
    IdentityRecoveryAdmissionDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_event_dto import (
    IdentityRecoveryEventDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.identity_recovery_admission_writer import (
    IdentityRecoveryAdmissionWriter,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_recovery_flow_id import (
    IdentityRecoveryFlowId,
)
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.infrastructure.mappers.postgres_human_credential_state_mapper import (
    PostgresHumanCredentialStateMapper,
)
from inframeld_backend.access.infrastructure.readers.human_credential_state_queries import (
    HumanCredentialStateQueries,
)
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
from inframeld_backend.access.infrastructure.rows.identity_recovery_proof_link_row import (
    IdentityRecoveryProofLinkRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

_RECOVERY_ADMISSION_TIMEOUT_SECONDS = 5.0


class PostgresIdentityRecoveryAdmissionWriter(IdentityRecoveryAdmissionWriter):
    """Coordinate linked recovery with Access changes in the caller's transaction.

    A five-second deadline covers database work. Identities without a local link
    still receive recovery records. The caller owns commit and rollback.
    """

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
    async def reserve(self, event: IdentityRecoveryEventDTO) -> IdentityRecoveryAdmissionDTO:
        if event.identity.authority != self._authority:
            raise ConflictError("The recovery event does not match the configured provider.")

        loop = asyncio.get_running_loop()
        deadline = loop.time() + _RECOVERY_ADMISSION_TIMEOUT_SECONDS
        try:
            async with asyncio.timeout_at(deadline):
                admission = await self._reserve(event)
                if loop.time() >= deadline:
                    raise TimeoutError()
                return admission
        except TimeoutError as error:
            raise DependencyUnavailableError(
                "Recovery admission exceeded its database deadline."
            ) from error

    async def _reserve(self, event: IdentityRecoveryEventDTO) -> IdentityRecoveryAdmissionDTO:
        await PostgresIdentityCoordinator(self._session).acquire(
            installation_id=self._installation_id, identity=event.identity
        )
        # An unlinked identity has no organization to lock and may still recover.
        await self._session.scalar(
            select(OrganizationRow.id)
            .join(
                HumanIdentityLinkRow,
                HumanIdentityLinkRow.organization_id == OrganizationRow.id,
            )
            .where(
                HumanIdentityLinkRow.authority == event.identity.authority.value,
                HumanIdentityLinkRow.subject == event.identity.subject.value,
            )
            .with_for_update(of=OrganizationRow)
        )

        prior_result = await self._session.execute(
            HumanCredentialStateQueries.for_identity(event.identity)
        )
        prior = prior_result.tuples().one_or_none()

        state = PostgresHumanCredentialStateMapper.to_state(event.identity, prior)
        if state.installation_id != self._installation_id:
            raise ConflictError("The installation identity does not match recovery configuration.")

        inserted = await self._session.scalar(
            insert(IdentityRecoveryAdmissionRow)
            .values(
                operation_id=str(uuid4()),
                installation_id=self._installation_id.value,
                authority=self._authority.value,
                flow_id=event.flow_id.value,
                subject=event.identity.subject.value,
                event_kind=event.event_kind,
            )
            .on_conflict_do_nothing(constraint="uq_identity_recovery_admissions_flow")
            .returning(IdentityRecoveryAdmissionRow.operation_id)
        )
        if inserted is not None:
            await self._session.execute(
                insert(IdentityRecoveryProofLinkRow).from_select(
                    [
                        "installation_id",
                        "authority",
                        "subject",
                        "covering_operation_id",
                        "covered_operation_id",
                    ],
                    select(
                        IdentityRecoveryAdmissionRow.installation_id,
                        IdentityRecoveryAdmissionRow.authority,
                        IdentityRecoveryAdmissionRow.subject,
                        literal(inserted),
                        IdentityRecoveryAdmissionRow.operation_id,
                    ).where(
                        IdentityRecoveryAdmissionRow.installation_id == self._installation_id.value,
                        IdentityRecoveryAdmissionRow.authority == self._authority.value,
                        IdentityRecoveryAdmissionRow.subject == event.identity.subject.value,
                        IdentityRecoveryAdmissionRow.operation_id != inserted,
                        IdentityRecoveryAdmissionRow.released_at.is_(None),
                    ),
                    include_defaults=False,
                )
            )

            if state.version is None and prior is not None and prior[3]:
                raise DependencyUnavailableError(
                    "Credential history requires its original version state."
                )

            await self._session.execute(
                insert(HumanCredentialVersionRow)
                .values(
                    installation_id=self._installation_id.value,
                    authority=self._authority.value,
                    subject=event.identity.subject.value,
                    version=1,
                )
                .on_conflict_do_nothing()
            )

            advanced = await self._session.scalar(
                update(HumanCredentialVersionRow)
                .where(
                    HumanCredentialVersionRow.installation_id == self._installation_id.value,
                    HumanCredentialVersionRow.authority == self._authority.value,
                    HumanCredentialVersionRow.subject == event.identity.subject.value,
                    HumanCredentialVersionRow.version < 2**63 - 1,
                )
                .values(version=HumanCredentialVersionRow.version + 1)
                .returning(HumanCredentialVersionRow.version)
            )

            if advanced is None:
                raise DependencyUnavailableError("The credential version cannot be advanced.")

        row = await self._session.scalar(
            select(IdentityRecoveryAdmissionRow).where(
                IdentityRecoveryAdmissionRow.installation_id == self._installation_id.value,
                IdentityRecoveryAdmissionRow.authority == self._authority.value,
                IdentityRecoveryAdmissionRow.flow_id == event.flow_id.value,
            )
        )
        if row is None:
            raise RuntimeError("The reserved recovery admission could not be read.")

        return IdentityRecoveryAdmissionDTO(
            event=IdentityRecoveryEventDTO(
                flow_id=IdentityRecoveryFlowId(row.flow_id),
                identity=VerifiedHumanIdentityDTO(
                    authority=IdentityAuthority(row.authority),
                    subject=IdentitySubject(row.subject),
                ),
                event_kind=row.event_kind,
            ),
            operation_id=OperationId(row.operation_id),
        )
