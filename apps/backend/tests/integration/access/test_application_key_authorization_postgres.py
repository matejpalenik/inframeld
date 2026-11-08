"""Prove current incoming keys and original admitted authority through ordinary persistence."""

import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import DateTime, Integer, String, column, delete, func, select, table, update
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession
from tests.support.application_key_scenarios import (
    ApplicationKeySeedDTO,
    seed_application_key,
    store_application_key,
)

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.admitted_work_authority_dto import (
    AdmittedWorkAuthorityDTO,
)
from inframeld_backend.access.application.dtos.application_key_verification_profile_dto import (
    ApplicationKeyVerificationProfileDTO,
)
from inframeld_backend.access.application.errors.application_key_credential_rejected_error import (
    ApplicationKeyCredentialRejectedError,
)
from inframeld_backend.access.application.services.action_authorization_service import (
    ActionAuthorizationService,
)
from inframeld_backend.access.application.services.admitted_work_authorization_service import (
    AdmittedWorkAuthorizationService,
)
from inframeld_backend.access.application.services.application_authentication_service import (
    ApplicationAuthenticationService,
)
from inframeld_backend.access.application.value_objects.application_key_credential import (
    ApplicationKeyCredential,
)
from inframeld_backend.access.domain.enums.application_key_adapter import ApplicationKeyAdapter
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.application_key_audience import (
    ApplicationKeyAudience,
)
from inframeld_backend.access.infrastructure.readers.postgres_admitted_work_facts_reader import (
    PostgresAdmittedWorkFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_application_authentication_facts_reader import (
    PostgresApplicationAuthenticationFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_action_facts_reader import (
    PostgresProjectActionFactsReader,
)
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.application_key_row import ApplicationKeyRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.verifiers.postgres_application_key_verifier import (
    PostgresApplicationKeyVerifier,
)
from inframeld_backend.access.infrastructure.writers.postgres_job_admission_audit_writer import (
    PostgresJobAdmissionAuditWriter,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.dtos.job_admission_dto import JobAdmissionDTO
from inframeld_backend.shared.application.dtos.product_job_binding_dto import ProductJobBindingDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.errors.application_errors import AccessDeniedError
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.application.services.job_admission_service import JobAdmissionService
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.job_payload import JobPayload
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.infrastructure.readers.postgres_installation_identity_reader import (
    PostgresInstallationIdentityReader,
)
from inframeld_backend.shared.infrastructure.repositories.postgres_job_store import PostgresJobStore
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires isolated PostgreSQL services",
    ),
]
PROFILE = ApplicationKeyVerificationProfileDTO(
    ApplicationKeyAudience("https://api.test"), ApplicationKeyAdapter.HTTP
)
ACTION = ActionId(ProjectAction.INSPECT_FEEDBACK.value)
PAYLOAD = JobPayload("test.progress", 1, b"fixed")
CONTEXT = IdempotencyContextDTO(
    HttpMethod.POST,
    "/test/projects/{project_id}/feedback-reports",
    IdempotencyKey("application-job"),
)
FINGERPRINT = RequestFingerprint(b"A" * 32)


def _service(session: AsyncSession) -> JobAdmissionService:
    return JobAdmissionService(
        ActionAuthorizationService(
            PostgresProjectActionFactsReader(session, application_key_profile=PROFILE)
        ),
        AdmittedWorkAuthorizationService(PostgresAdmittedWorkFactsReader(session)),
        IdempotencyService(PostgresOperationReservationWriter(session)),
        PostgresJobStore(session),
        PostgresJobAdmissionAuditWriter(session),
        supported_payloads=((PAYLOAD.kind, PAYLOAD.version),),
    )


async def _authenticate(
    database: Database, credential: ApplicationKeyCredential
) -> AccessContextDTO:
    return await ApplicationAuthenticationService(
        key_verifier=PostgresApplicationKeyVerifier(database),
        authentication_facts_reader=PostgresApplicationAuthenticationFactsReader(database),
        verification_profile=PROFILE,
    ).authenticate(credential)


async def _scenario(
    database: Database,
) -> tuple[ApplicationKeySeedDTO, AccessContextDTO, AdmittedWorkAuthorityDTO]:
    seed = await seed_application_key(database)
    async with database.session() as session, session.begin():
        session.add(
            ProjectActionGrantRow(
                project_id=seed.account.project_id.value,
                recipient_principal_id=seed.account.principal_id.value,
                recipient_kind=PrincipalKind.APPLICATION,
                action=ACTION.value,
                can_grant=False,
            )
        )
    authority = AdmittedWorkAuthorityDTO(
        principal_id=seed.account.principal_id,
        principal_kind=PrincipalKind.APPLICATION,
        installation_id=await PostgresInstallationIdentityReader(database).read(),
        organization_id=seed.account.organization_id,
        project_id=seed.account.project_id,
        action_id=ACTION,
        human_binding=None,
    )
    return seed, await _authenticate(database, seed.credential), authority


async def _admit(
    database: Database,
    access: AccessContextDTO,
    authority: AdmittedWorkAuthorityDTO,
    request_id: RequestId,
) -> JobAdmissionDTO:
    async with database.session() as session, session.begin():
        return await _service(session).admit(
            access=access,
            authority=authority,
            context=CONTEXT,
            fingerprint=FINGERPRINT,
            request_id=request_id,
            payload=PAYLOAD,
        )


async def _wait_for_key_lock(
    database: Database, task: asyncio.Task[JobAdmissionDTO] | asyncio.Task[None], holder_pid: int
) -> None:
    pid, name = column("pid", Integer), column("datname", String)
    activity = table("pg_stat_activity", pid, name)
    async with asyncio.timeout(3):
        while not task.done():
            async with database.session() as observer:
                blocked = await observer.scalar(
                    select(pid)
                    .select_from(activity)
                    .where(
                        name == func.current_database(type_=String()),
                        func.pg_blocking_pids(pid, type_=ARRAY(Integer)).contains([holder_pid]),
                    )
                )
            if blocked is not None:
                return
            await asyncio.sleep(0.01)
    try:
        task.result()
    except BaseException as error:
        raise AssertionError("The operation failed before its required key-lock wait.") from error
    pytest.fail("The operation bypassed its required current-key coordination.")


@pytest.mark.parametrize("expire", [False, True], ids=["revoked-origin", "expired-origin"])
async def test_committed_admission_retains_original_actor_and_replays_only_with_current_key(
    database: Database, expire: bool
) -> None:
    seed, access, authority = await _scenario(database)
    request_id = RequestId(uuid4())
    change_task: asyncio.Task[None] | None = None
    original: JobAdmissionDTO | None = None

    async def change_origin() -> None:
        async with database.session() as session, session.begin():
            await session.execute(
                update(ApplicationKeyRow)
                .where(ApplicationKeyRow.key_id == seed.credential.key_id.value)
                .values(
                    {
                        ApplicationKeyRow.expires_at
                        if expire
                        else ApplicationKeyRow.revoked_at: func.clock_timestamp(
                            type_=DateTime(timezone=True)
                        )
                    }
                )
            )

    try:
        async with database.session() as caller, caller.begin():
            original = await _service(caller).admit(
                access=access,
                authority=authority,
                context=CONTEXT,
                fingerprint=FINGERPRINT,
                request_id=request_id,
                payload=PAYLOAD,
            )
            holder_pid = await caller.scalar(select(func.pg_backend_pid(type_=Integer)))
            assert holder_pid is not None
            change_task = asyncio.create_task(change_origin())
            await _wait_for_key_lock(database, change_task, holder_pid)
        async with asyncio.timeout(3):
            await change_task
    finally:
        if change_task is not None:
            async with asyncio.timeout(3):
                if not change_task.done():
                    change_task.cancel()
                outcome = (
                    await asyncio.shield(asyncio.gather(change_task, return_exceptions=True))
                )[0]
            if isinstance(outcome, BaseException) and not isinstance(
                outcome, asyncio.CancelledError
            ):
                raise outcome
    assert original is not None and original.created

    # A stale, originally authenticated context cannot recover the protected receipt.
    with pytest.raises(ApplicationKeyCredentialRejectedError):
        await _admit(database, access, authority, RequestId(uuid4()))
    replacement = await store_application_key(
        database,
        principal_id=seed.account.principal_id,
        organization_id=seed.account.organization_id,
        project_id=seed.account.project_id,
        issued_by=seed.creator_access.actor_principal_id,
    )
    replacement_access = await _authenticate(database, replacement)
    replay = await _admit(database, replacement_access, authority, RequestId(uuid4()))
    assert (replay.job_id, replay.operation_id, replay.created) == (
        original.job_id,
        original.operation_id,
        False,
    )

    async with database.session() as session, session.begin():
        saved = await PostgresJobStore(session).find(original.operation_id)
        assert saved is not None and isinstance(saved.binding, ProductJobBindingDTO)
        assert saved.binding.authority == authority and saved.binding.request_id == request_id
        assert saved.payload == PAYLOAD and saved.binding.authority.human_binding is None
        assert seed.credential.value not in repr(saved) and replacement.value not in repr(saved)
        await AdmittedWorkAuthorizationService(
            PostgresAdmittedWorkFactsReader(session)
        ).require_current(saved.binding.authority)
        assert (
            await session.scalar(
                select(func.count())
                .select_from(DurableJobRow)
                .where(DurableJobRow.operation_id == original.operation_id.value)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(AccessAuditEventRow.correlation_id == original.operation_id.value)
            )
            == 1
        )

    async with database.session() as session, session.begin():
        await session.execute(
            delete(ProjectActionGrantRow).where(
                ProjectActionGrantRow.project_id == authority.project_id.value,
                ProjectActionGrantRow.recipient_principal_id == authority.principal_id.value,
                ProjectActionGrantRow.action == ACTION.value,
            )
        )
    with pytest.raises(AccessDeniedError):
        await _admit(database, replacement_access, authority, RequestId(uuid4()))
    async with database.session() as session, session.begin():
        with pytest.raises(AccessDeniedError):
            await AdmittedWorkAuthorizationService(
                PostgresAdmittedWorkFactsReader(session)
            ).require_current(authority)


@pytest.mark.parametrize("expire", [False, True], ids=["revocation-wins", "post-wait-expiry"])
async def test_key_change_winning_admission_order_leaves_no_reservation_or_job(
    database: Database, expire: bool
) -> None:
    seed, access, authority = await _scenario(database)
    task: asyncio.Task[JobAdmissionDTO] | None = None
    with pytest.raises(ApplicationKeyCredentialRejectedError):
        try:
            async with database.session() as holder, holder.begin():
                holder_pid = await holder.scalar(select(func.pg_backend_pid(type_=Integer)))
                assert holder_pid is not None
                await holder.execute(
                    update(ApplicationKeyRow)
                    .where(ApplicationKeyRow.key_id == seed.credential.key_id.value)
                    .values(http_audience=PROFILE.audience.value)
                )
                task = asyncio.create_task(_admit(database, access, authority, RequestId(uuid4())))
                await _wait_for_key_lock(database, task, holder_pid)
                await holder.execute(
                    update(ApplicationKeyRow)
                    .where(ApplicationKeyRow.key_id == seed.credential.key_id.value)
                    .values(
                        {
                            ApplicationKeyRow.expires_at
                            if expire
                            else ApplicationKeyRow.revoked_at: func.clock_timestamp(
                                type_=DateTime(timezone=True)
                            )
                        }
                    )
                )
            async with asyncio.timeout(3):
                await task
        finally:
            if task is not None:
                async with asyncio.timeout(3):
                    if not task.done():
                        task.cancel()
                    outcome = (await asyncio.shield(asyncio.gather(task, return_exceptions=True)))[
                        0
                    ]
                if isinstance(outcome, BaseException) and not isinstance(
                    outcome, asyncio.CancelledError
                ):
                    raise outcome
    async with database.session() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(IdempotencyReservationRow)
                .where(
                    IdempotencyReservationRow.principal_id == authority.principal_id.value,
                    IdempotencyReservationRow.request_key == CONTEXT.key.value,
                )
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(DurableJobRow)
                .where(DurableJobRow.principal_id == authority.principal_id.value)
            )
            == 0
        )
