import asyncio
from typing import override
from uuid import UUID

from sqlalchemy import Nullable, and_, func, or_, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.shared.application.dtos.operation_reservation_result_dto import (
    OperationReservationResultDTO,
)
from inframeld_backend.shared.application.dtos.original_operation_lookup_record_dto import (
    OriginalOperationLookupRecordDTO,
)
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.protocols.operation_lookup_reader import (
    OperationLookupReader,
)
from inframeld_backend.shared.application.queries.lookup_original_operation_query import (
    LookupOriginalOperationQuery,
)
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class PostgresOperationLookupReader(OperationLookupReader):
    """Observe one retained binding without writing, repairing or extending history."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def read(
        self, *, principal_id: PrincipalId, query: LookupOriginalOperationQuery
    ) -> OriginalOperationLookupRecordDTO | None:
        row = IdempotencyReservationRow
        job = DurableJobRow
        identity = HumanIdentityLinkRow
        binding = and_(
            row.principal_id == principal_id.value,
            row.organization_id == query.organization_id.value,
            row.project_id.is_not_distinct_from(
                query.project_id.value if query.project_id is not None else None
            ),
            row.method == query.method,
            row.requested_route == query.requested_route,
            row.request_key == query.key.value,
            row.lookup_authority_family == query.expected_authority.family.value,
            row.lookup_action_id == query.expected_authority.action_id.value,
            or_(
                row.state != OperationReservationState.REPLAYABLE,
                row.expires_at.is_(None),
                row.expires_at > func.clock_timestamp(),
            ),
        )
        statement = (
            select(
                InstallationIdentityRow.installation_id,
                Nullable(row.operation_id),
                Nullable(row.state),
                Nullable(row.replay_kind),
                Nullable(row.expires_at),
                Nullable(job.id),
                Nullable(job.human_authority),
                Nullable(job.human_subject),
                Nullable(job.human_version),
                Nullable(identity.principal_id),
            )
            .select_from(InstallationIdentityRow)
            .outerjoin(row, binding)
            .outerjoin(
                job,
                and_(
                    row.state == OperationReservationState.REPLAYABLE,
                    row.replay_kind == OperationReplayKind.ASYNC_JOB,
                    row.lookup_authority_family
                    == OperationLookupAuthorityFamily.PROJECT_ACTION_USE.value,
                    job.operation_id == row.operation_id,
                    job.binding_kind == "product",
                    job.cleanup_obligation_id.is_(None),
                    job.installation_id == InstallationIdentityRow.installation_id,
                    job.principal_id == row.principal_id,
                    job.principal_kind == PrincipalKind.HUMAN.value,
                    job.organization_id == row.organization_id,
                    job.project_id == row.project_id,
                    job.action_id == row.lookup_action_id,
                ),
            )
            .outerjoin(
                identity,
                and_(
                    identity.authority == job.human_authority,
                    identity.subject == job.human_subject,
                    identity.principal_id == job.principal_id,
                    identity.organization_id == job.organization_id,
                    identity.principal_kind == PrincipalKind.HUMAN,
                ),
            )
            .where(InstallationIdentityRow.singleton_key == 1)
        )
        try:
            async with asyncio.timeout(5.0):
                observed = (await self._session.execute(statement)).tuples().one_or_none()
        except (TimeoutError, OperationalError, SqlAlchemyTimeoutError, LookupError):
            raise DependencyUnavailableError() from None
        if observed is None:
            raise DependencyUnavailableError()

        (
            installed,
            operation_id,
            state,
            replay_kind,
            expiry,
            job_id,
            human_authority,
            human_subject,
            human_version,
            linked_principal,
        ) = observed
        if installed != query.installation_id.value or operation_id is None:
            return None
        if state is None:
            raise DependencyUnavailableError()
        return OriginalOperationLookupRecordDTO(
            OperationReservationResultDTO(
                OperationId(operation_id), False, state, replay_kind, expiry
            ),
            self._job_reference(
                job_id, human_authority, human_subject, human_version, linked_principal
            ),
        )

    @staticmethod
    def _job_reference(
        job_id: UUID | None,
        authority: str | None,
        subject: str | None,
        version: int | None,
        linked_principal: UUID | None,
    ) -> JobId | None:
        if (
            job_id is None
            or authority is None
            or subject is None
            or version is None
            or linked_principal is None
        ):
            return None
        try:
            IdentityAuthority(authority)
            IdentitySubject(subject)
            # Original admission can precede recovery. Current credential
            # eligibility was checked independently before this projection.
            HumanCredentialVersion(version)
            return JobId(job_id)
        except (TypeError, ValueError):
            return None
