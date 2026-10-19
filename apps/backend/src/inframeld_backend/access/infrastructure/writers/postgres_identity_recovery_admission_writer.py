import asyncio
from typing import override
from uuid import uuid4

from sqlalchemy import select
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
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_admission_row import (
    IdentityRecoveryAdmissionRow,
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

        await self._session.execute(
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
        )
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
