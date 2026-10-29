"""Qualify exact retained binding and pre-search current authority in PostgreSQL.

Synthetic canonical routes exercise shared admission support. They do not deliver
an upload, build or Organization business endpoint.
"""

import os
from dataclasses import replace
from datetime import timedelta

import pytest
from sqlalchemy import func, select, update
from tests.support.access_scenarios import MockAccessScenarios
from tests.support.authentication_evidence import MockAuthenticationEvidence

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_operation_admission_request_dto import (
    ProjectOperationAdmissionRequestDTO,
)
from inframeld_backend.access.application.services.action_authorization_service import (
    ActionAuthorizationService,
)
from inframeld_backend.access.application.services.operation_lookup_authorization_service import (
    OperationLookupAuthorizationService,
)
from inframeld_backend.access.application.services.project_operation_admission_service import (
    ProjectOperationAdmissionService,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.infrastructure.readers.postgres_operation_lookup_facts_reader import (
    PostgresOperationLookupFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_action_facts_reader import (
    PostgresProjectActionFactsReader,
)
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.shared.application.dtos.accepted_async_operation_dto import (
    AcceptedAsyncOperationDTO,
)
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
)
from inframeld_backend.shared.application.dtos.operation_reservation_request_dto import (
    OperationReservationRequestDTO,
)
from inframeld_backend.shared.application.dtos.unresolved_operation_dto import (
    UnresolvedOperationDTO,
)
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
)
from inframeld_backend.shared.application.queries.lookup_original_operation_query import (
    LookupOriginalOperationQuery,
)
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.application.services.original_operation_lookup_service import (
    OriginalOperationLookupService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.infrastructure.readers.postgres_installation_identity_reader import (
    PostgresInstallationIdentityReader,
)
from inframeld_backend.shared.infrastructure.readers.postgres_operation_lookup_reader import (
    PostgresOperationLookupReader,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires PostgreSQL integration services",
)
ACTION = ActionId("create-access-groups")


async def admitted(
    database: Database, kind: OperationReplayKind | None = OperationReplayKind.ASYNC_JOB
) -> tuple[AccessContextDTO, LookupOriginalOperationQuery, str]:
    async with database.session() as session, session.begin():
        seed = await MockAccessScenarios.seed_project_authorization(
            session, is_project_member=True, has_action_grant=False
        )
        session.add(
            ProjectActionGrantRow(
                project_id=seed.project_id.value,
                recipient_principal_id=seed.principal_id.value,
                recipient_kind=PrincipalKind.HUMAN,
                action=ACTION.value,
                can_grant=True,
            )
        )
    access = AccessContextDTO(seed.principal_id, MockAuthenticationEvidence.browser())
    installed = await PostgresInstallationIdentityReader(database).read()
    query = LookupOriginalOperationQuery(
        installed,
        seed.organization_id,
        seed.project_id,
        "POST",
        "/v1/original-project-operation",
        IdempotencyKey("lost-ack"),
        OperationLookupAuthority(OperationLookupAuthorityFamily.PROJECT_ACTION_USE, ACTION),
    )
    async with database.session() as session, session.begin():
        idempotency = IdempotencyService(PostgresOperationReservationWriter(session))
        reservation = await ProjectOperationAdmissionService(
            ActionAuthorizationService(PostgresProjectActionFactsReader(session)), idempotency
        ).reserve(
            access=access,
            action_id=ACTION,
            request=ProjectOperationAdmissionRequestDTO(
                seed.project_id,
                query.method,
                query.requested_route,
                query.key,
                RequestFingerprint(b"F" * 32),
            ),
            expected_replay_kind=kind or OperationReplayKind.SAFE_RESULT,
        )
        assert isinstance(reservation, NewOperationReservationDTO)
        if kind is not None:
            await idempotency.record_completed_result(reservation, replay_kind=kind)
    return access, query, reservation.operation_id.value


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", list(OperationReplayKind))
async def test_retained_outcome_can_be_read_without_reserving_again(
    database: Database, kind: OperationReplayKind
) -> None:
    access, query, operation = await admitted(database, kind)
    async with database.session() as session:
        before = (
            (
                await session.execute(
                    select(
                        IdempotencyReservationRow.operation_id,
                        IdempotencyReservationRow.created_at,
                        IdempotencyReservationRow.expires_at,
                    )
                )
            )
            .tuples()
            .all()
        )
        result = await PostgresOperationLookupReader(session).read(
            principal_id=access.actor_principal_id, query=query
        )
        assert result is not None
        assert result.operation_id.value == operation
        assert result.created is False
        assert result.replay_kind is kind
        after = (
            (
                await session.execute(
                    select(
                        IdempotencyReservationRow.operation_id,
                        IdempotencyReservationRow.created_at,
                        IdempotencyReservationRow.expires_at,
                    )
                )
            )
            .tuples()
            .all()
        )
        assert after == before


@pytest.mark.asyncio
async def test_original_action_binding_is_saved_with_admission(database: Database) -> None:
    _access, query, operation = await admitted(database)
    async with database.session() as session:
        row = await session.get(IdempotencyReservationRow, operation)
        assert row is not None
        assert row.lookup_authority_family == query.expected_authority.family.value
        assert row.lookup_action_id == ACTION.value


@pytest.mark.asyncio
async def test_async_lookup_keeps_admission_and_explicitly_has_no_known_job(
    database: Database,
) -> None:
    access, query, operation = await admitted(database)
    async with database.session() as session:
        service = OriginalOperationLookupService(
            OperationLookupAuthorizationService(PostgresOperationLookupFactsReader(session)),
            PostgresOperationLookupReader(session),
        )
        result = await service.lookup(access=access, query=query)
    assert isinstance(result, AcceptedAsyncOperationDTO)
    assert result.operation_id.value == operation
    assert result.expires_at is None


@pytest.mark.asyncio
@pytest.mark.parametrize("history", ["retained", "absent", "legacy", "different_guard"])
async def test_denied_guard_is_independent_of_history(database: Database, history: str) -> None:
    access, query, operation = await admitted(database)
    assert query.project_id is not None
    async with database.session() as session, session.begin():
        await session.execute(
            update(ProjectActionGrantRow)
            .where(ProjectActionGrantRow.project_id == query.project_id.value)
            .values(can_grant=False)
        )
        if history == "absent":
            query = replace(query, key=IdempotencyKey("absent"))
        elif history == "legacy":
            await session.execute(
                update(IdempotencyReservationRow)
                .where(IdempotencyReservationRow.operation_id == operation)
                .values(lookup_authority_family=None, lookup_action_id=None)
            )
        query = replace(
            query,
            requested_route="/v1/projects/{project_id}/grants",
            expected_authority=OperationLookupAuthority(
                OperationLookupAuthorityFamily.PROJECT_GRANT_READ, ACTION
            ),
        )
    async with database.session() as session:
        with pytest.raises(AccessDeniedError):
            await OriginalOperationLookupService(
                OperationLookupAuthorizationService(PostgresOperationLookupFactsReader(session)),
                PostgresOperationLookupReader(session),
            ).lookup(access=access, query=query)


@pytest.mark.asyncio
@pytest.mark.parametrize("history", ["absent", "legacy", "different_guard", "expired"])
async def test_authorized_nonmatches_are_uniformly_unresolved(
    database: Database, history: str
) -> None:
    access, query, operation = await admitted(database, OperationReplayKind.SAFE_RESULT)
    async with database.session() as session, session.begin():
        if history == "absent":
            query = replace(query, key=IdempotencyKey("absent"))
        elif history == "legacy":
            await session.execute(
                update(IdempotencyReservationRow)
                .where(IdempotencyReservationRow.operation_id == operation)
                .values(lookup_authority_family=None, lookup_action_id=None)
            )
        elif history == "different_guard":
            await session.execute(
                update(IdempotencyReservationRow)
                .where(IdempotencyReservationRow.operation_id == operation)
                .values(lookup_authority_family="project_grant_read")
            )
        else:
            await session.execute(
                update(IdempotencyReservationRow)
                .where(IdempotencyReservationRow.operation_id == operation)
                .values(expires_at=func.clock_timestamp() - timedelta(seconds=1))
            )
    async with database.session() as session:
        result = await OriginalOperationLookupService(
            OperationLookupAuthorizationService(PostgresOperationLookupFactsReader(session)),
            PostgresOperationLookupReader(session),
        ).lookup(access=access, query=query)
    assert result == UnresolvedOperationDTO()


@pytest.mark.asyncio
async def test_retry_cannot_rewrite_original_authority(database: Database) -> None:
    access, query, _operation = await admitted(database)
    changed = OperationLookupAuthority(
        OperationLookupAuthorityFamily.PROJECT_ACTION_USE, ActionId("inspect-budget")
    )
    async with database.session() as session, session.begin():
        with pytest.raises(ConflictError):
            await PostgresOperationReservationWriter(session).reserve(
                OperationReservationRequestDTO(
                    principal_id=access.actor_principal_id,
                    organization_id=query.organization_id,
                    project_id=query.project_id,
                    method=query.method,
                    requested_route=query.requested_route,
                    key=query.key,
                    fingerprint=b"F" * 32,
                    lookup_authority=changed,
                )
            )


@pytest.mark.asyncio
async def test_in_progress_and_recovery_remain_distinct(database: Database) -> None:
    access, query, operation = await admitted(database, None)
    async with database.session() as session:
        result = await PostgresOperationLookupReader(session).read(
            principal_id=access.actor_principal_id, query=query
        )
        assert result is not None and result.state is OperationReservationState.IN_PROGRESS
    async with database.session() as session, session.begin():
        await PostgresOperationReservationWriter(session).mark_recovery_required(
            result.operation_id
        )
    async with database.session() as session:
        result = await PostgresOperationLookupReader(session).read(
            principal_id=access.actor_principal_id, query=query
        )
        assert result is not None and result.state is OperationReservationState.RECOVERY_REQUIRED
        assert result.operation_id.value == operation
