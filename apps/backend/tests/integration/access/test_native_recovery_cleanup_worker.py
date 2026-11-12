"""Join native Kratos evidence to the real recovery command and real Hydra cleanup."""

import asyncio
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import replace
from uuid import UUID, uuid4

import httpx2
import pytest
from pydantic import HttpUrl, SecretStr, TypeAdapter
from sqlalchemy import select
from tests.support.access_scenarios import MockAccessScenarios
from tests.support.busy_application_job import busy_application_job
from tests.support.hydra_provider import API_AUDIENCE, HYDRA_ISSUER, hydra_test_provider
from tests.support.integration_services import HYDRA_ADMIN_URL, HYDRA_PUBLIC_URL
from tests.support.kratos_browser import create_browser, login_human, register_human
from tests.support.kratos_recovery import (
    redeem_recovery_code,
    request_recovery_code,
    wait_for_recovery_code,
)
from tests.support.kratos_settings import read_recovery_settings, submit_password_settings
from tests.support.maintenance_command import run_maintenance
from tests.support.recovery_worker_process import (
    EXECUTION_DATABASE,
    EXECUTION_PUBLIC,
    recovery_worker_process,
)

from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState as State,
)
from inframeld_backend.access.domain.enums.organization_action import OrganizationAction
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.infrastructure.readers.postgres_human_credential_state_reader import (
    PostgresHumanCredentialStateReader,
)
from inframeld_backend.access.infrastructure.rows.host_maintenance_receipt_row import (
    HostMaintenanceReceiptRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_admission_row import (
    IdentityRecoveryAdmissionRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_cleanup_run_row import (
    IdentityRecoveryCleanupRunRow,
)
from inframeld_backend.access.infrastructure.rows.organization_action_grant_row import (
    OrganizationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.settings.hydra_settings import HydraSettings
from inframeld_backend.access.infrastructure.settings.kratos_settings import KratosSettings
from inframeld_backend.access.infrastructure.writers.postgres_human_credential_state_initializer import (
    PostgresHumanCredentialStateInitializer,
)
from inframeld_backend.bootstrap.application_factory import create_app
from inframeld_backend.bootstrap.application_settings import get_settings
from inframeld_backend.shared.domain.enums.job_status import JobStatus
from inframeld_backend.shared.infrastructure.repositories.postgres_job_store import PostgresJobStore
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.durable_job_attempt_row import (
    DurableJobAttemptRow,
)
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow
from inframeld_backend.shared.infrastructure.rows.human_suspension_obligation_row import (
    HumanSuspensionObligationRow,
)

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_KRATOS_INTEGRATION") != "1",
    reason="Requires the private native worker qualification graph",
)
AUTHORITY = IdentityAuthority(EXECUTION_PUBLIC)


@asynccontextmanager
async def _database() -> AsyncGenerator[Database]:
    database = Database(EXECUTION_DATABASE)
    await database.startup()
    try:
        yield database
    finally:
        await database.shutdown()


@asynccontextmanager
async def _api() -> AsyncGenerator[httpx2.AsyncClient]:
    settings = get_settings().model_copy(
        update={
            "database": EXECUTION_DATABASE,
            "kratos": KratosSettings(
                public_url=HttpUrl(EXECUTION_PUBLIC),
                admin_url=HttpUrl("http://kratos-recovery-execution:4434"),
                authority=AUTHORITY,
            ),
            "hydra": HydraSettings(
                admin_url=HttpUrl(HYDRA_ADMIN_URL),
                public_url=HttpUrl(HYDRA_PUBLIC_URL),
                issuer=HYDRA_ISSUER,
                api_audience=API_AUDIENCE,
            ),
        }
    )
    app = create_app(settings)
    async with (
        app.router.lifespan_context(app),
        httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url=API_AUDIENCE.value, timeout=5
        ) as api,
    ):
        yield api


async def _binding(database: Database, subject: IdentitySubject) -> HumanOAuthCredentialBindingDTO:
    identity = VerifiedHumanIdentityDTO(AUTHORITY, subject)
    state = await PostgresHumanCredentialStateInitializer(database).initialize(identity)
    assert state.version is not None
    return HumanOAuthCredentialBindingDTO(identity, state.installation_id, state.version)


async def _wait_for_release(
    database: Database, subject: IdentitySubject
) -> IdentityRecoveryAdmissionRow:
    async with asyncio.timeout(20):
        while True:
            async with database.session() as session:
                row = await session.scalar(
                    select(IdentityRecoveryAdmissionRow).where(
                        IdentityRecoveryAdmissionRow.subject == subject.value
                    )
                )
            if row is not None and row.released_at is not None:
                return row
            await asyncio.sleep(0.05)


async def _wait_for_suspension_status(
    database: Database,
    original_id: UUID,
    status: JobStatus,
) -> tuple[HumanSuspensionObligationRow, DurableJobRow]:
    async with asyncio.timeout(20):
        while True:
            async with database.session() as session:
                original, job = (
                    await session.execute(
                        select(HumanSuspensionObligationRow, DurableJobRow)
                        .join(
                            DurableJobRow, DurableJobRow.id == HumanSuspensionObligationRow.job_id
                        )
                        .where(
                            HumanSuspensionObligationRow.id == original_id,
                            DurableJobRow.suspension_obligation_id == original_id,
                        )
                    )
                ).one()
            if job.status == status.value:
                return original, job
            await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_native_evidence_real_cleanup_and_late_old_version_credentials_after_release() -> (
    None
):
    async with (
        asyncio.timeout(30),
        _database() as database,
        _api() as api,
        hydra_test_provider(kratos_public_url=EXECUTION_PUBLIC) as provider,
        create_browser(public_url=EXECUTION_PUBLIC) as owner,
        create_browser(public_url=EXECUTION_PUBLIC) as recovery_browser,
        create_browser(public_url=EXECUTION_PUBLIC) as bob_browser,
    ):
        alice = await register_human(owner)
        bob = await register_human(bob_browser)
        async with database.session() as session, session.begin():
            await MockAccessScenarios.seed_linked_human(
                session, VerifiedHumanIdentityDTO(AUTHORITY, alice.subject)
            )
            await MockAccessScenarios.seed_linked_human(
                session, VerifiedHumanIdentityDTO(AUTHORITY, bob.subject)
            )
        old_binding = await _binding(database, alice.subject)
        bob_binding = await _binding(database, bob.subject)
        old_tokens = await provider.issue_tokens(alice, credential_binding=old_binding)
        bob_tokens = await provider.issue_tokens(bob, credential_binding=bob_binding)
        # This test-only login captures identity before recovery without approving it.
        # Production consent's delayed captured-binding case remains covered separately.
        pending_login = await provider.begin_login(alice)
        assert (
            await api.get(
                "/v1/session", headers={"Authorization": f"Bearer {old_tokens.access_token.value}"}
            )
        ).status_code == 200

        flow = await request_recovery_code(recovery_browser, alice.email)
        redeemed = await redeem_recovery_code(
            recovery_browser, flow, await wait_for_recovery_code(alice.email)
        )
        settings = await read_recovery_settings(
            recovery_browser, redeemed, public_url=EXECUTION_PUBLIC
        )
        async with database.session() as session:
            original = await session.scalar(
                select(IdentityRecoveryAdmissionRow).where(
                    IdentityRecoveryAdmissionRow.subject == alice.subject.value
                )
            )
            assert (
                original is not None
                and original.kratos_cleanup_state is State.PENDING
                and original.released_at is None
            )
        password = SecretStr(f"Replacement-{uuid4().hex}!")
        saved = await submit_password_settings(
            recovery_browser, settings, password, public_url=EXECUTION_PUBLIC
        )
        assert saved.status_code == 200

        async with busy_application_job(database) as ordinary, recovery_worker_process():
            finished = await _wait_for_release(database, alice.subject)
            async with database.session() as session, session.begin():
                still_owned = await PostgresJobStore(session).require_current(ordinary)
            assert still_owned.status is JobStatus.RUNNING
        assert finished.operation_id == original.operation_id
        assert finished.kratos_cleanup_state is finished.hydra_cleanup_state is State.CONFIRMED
        assert not await provider.token_is_active(old_tokens.access_token)
        assert await provider.refresh_tokens(old_tokens) is None
        assert (await owner.get("/sessions/whoami")).status_code == 401
        assert (await recovery_browser.get("/sessions/whoami")).status_code == 200
        assert (await bob_browser.get("/sessions/whoami")).status_code == 200

        late_code = await provider.approve_login_and_consent(
            pending_login, credential_binding=old_binding
        )
        late_tokens = await provider.exchange_authorization_code(late_code)
        assert late_tokens is not None and await provider.token_is_active(late_tokens.access_token)
        tokens = late_tokens
        for index in range(2):
            assert tokens is not None
            await provider.assert_token_binding(tokens.access_token, binding=old_binding)
            denied = await api.get(
                "/v1/session", headers={"Authorization": f"Bearer {tokens.access_token.value}"}
            )
            assert denied.status_code == 401
            assert 'error="invalid_token"' in denied.headers["www-authenticate"]
            if index == 0:
                tokens = await provider.refresh_tokens(tokens)

        cookie = recovery_browser.cookies.get("ory_kratos_session")
        assert cookie is not None
        recovered = replace(
            alice, password=password.get_secret_value(), credential=BrowserSessionCredential(cookie)
        )
        current_binding = await _binding(database, alice.subject)
        assert current_binding.version.value == old_binding.version.value + 1
        fresh = await provider.issue_tokens(recovered, credential_binding=current_binding)
        assert (
            await api.get(
                "/v1/session", headers={"Authorization": f"Bearer {fresh.access_token.value}"}
            )
        ).status_code == 200
        bob_refreshed = await provider.refresh_tokens(bob_tokens)
        assert bob_refreshed is not None
        assert (
            await api.get(
                "/v1/session",
                headers={"Authorization": f"Bearer {bob_refreshed.access_token.value}"},
            )
        ).status_code == 200


@pytest.mark.asyncio
async def test_replacement_process_preserves_original_budget_after_hydra_was_unavailable() -> None:
    async with (
        asyncio.timeout(60),
        _database() as database,
        create_browser(public_url=EXECUTION_PUBLIC) as owner,
        create_browser(public_url=EXECUTION_PUBLIC) as recovery_browser,
    ):
        alice = await register_human(owner)
        flow = await request_recovery_code(recovery_browser, alice.email)
        redeemed = await redeem_recovery_code(
            recovery_browser, flow, await wait_for_recovery_code(alice.email)
        )
        settings = await read_recovery_settings(
            recovery_browser, redeemed, public_url=EXECUTION_PUBLIC
        )
        saved = await submit_password_settings(
            recovery_browser,
            settings,
            SecretStr(f"Replacement-{uuid4().hex}!"),
            public_url=EXECUTION_PUBLIC,
        )
        assert saved.status_code == 200
        async with recovery_worker_process(admin_url="http://127.0.0.1:1"):
            async with asyncio.timeout(30):
                while True:
                    async with database.session() as session:
                        result = (
                            await session.execute(
                                select(IdentityRecoveryCleanupRunRow, IdentityRecoveryAdmissionRow)
                                .join(
                                    IdentityRecoveryAdmissionRow,
                                    IdentityRecoveryAdmissionRow.operation_id
                                    == IdentityRecoveryCleanupRunRow.operation_id,
                                )
                                .where(IdentityRecoveryAdmissionRow.subject == alice.subject.value)
                            )
                        ).one()
                        run, admission = result
                    if run.consumed_attempts == 1 and run.next_attempt_at > run.authorized_at:
                        assert run.ended_at is None and admission.released_at is None
                        original = (
                            run.id,
                            run.authorized_at,
                            run.deadline,
                            run.next_attempt_at,
                            admission.operation_id,
                        )
                        break
                    await asyncio.sleep(0.05)
        async with recovery_worker_process():
            finished = await _wait_for_release(database, alice.subject)
        async with database.session() as session:
            run = await session.get(IdentityRecoveryCleanupRunRow, original[0])
            assert run is not None and run.consumed_attempts == 2
            assert (run.id, run.authorized_at, run.deadline) == original[:3]
            assert run.terminal_reason == "cleanup_confirmed"
            assert finished.operation_id == original[4]


@pytest.mark.asyncio
async def test_host_command_resumes_ended_run_then_real_hydra_cleanup_releases_original() -> None:
    from sqlalchemy import func
    from tests.support.integration_services import RECOVERY_HOOKS_URL

    from inframeld_backend.shared.infrastructure.readers.postgres_installation_identity_reader import (
        PostgresInstallationIdentityReader,
    )

    async with (
        asyncio.timeout(60),
        _database() as database,
        create_browser(public_url=EXECUTION_PUBLIC) as owner,
        create_browser(public_url=EXECUTION_PUBLIC) as recovery_browser,
        hydra_test_provider(kratos_public_url=EXECUTION_PUBLIC) as hydra,
    ):
        alice = await register_human(owner)
        tokens = await hydra.issue_tokens(alice)
        assert await hydra.token_is_active(tokens.access_token)
        flow = await request_recovery_code(recovery_browser, alice.email)
        redeemed = await redeem_recovery_code(
            recovery_browser, flow, await wait_for_recovery_code(alice.email)
        )
        settings = await read_recovery_settings(
            recovery_browser, redeemed, public_url=EXECUTION_PUBLIC
        )
        password = SecretStr(f"Replacement-{uuid4().hex}!")
        saved = await submit_password_settings(
            recovery_browser,
            settings,
            password,
            public_url=EXECUTION_PUBLIC,
        )
        assert saved.status_code == 200

        # A real HTTP server without Hydra's admin routes explicitly rejects cleanup.
        async with recovery_worker_process(admin_url=RECOVERY_HOOKS_URL):
            async with asyncio.timeout(30):
                while True:
                    async with database.session() as session:
                        original = await session.scalar(
                            select(IdentityRecoveryAdmissionRow).where(
                                IdentityRecoveryAdmissionRow.subject == alice.subject.value
                            )
                        )
                        assert original is not None
                        failed = await session.scalar(
                            select(IdentityRecoveryCleanupRunRow).where(
                                IdentityRecoveryCleanupRunRow.operation_id == original.operation_id
                            )
                        )
                    if failed is not None and failed.ended_at is not None:
                        assert failed.terminal_reason == "permanent_provider_rejection"
                        assert failed.consumed_attempts == 1 and original.released_at is None
                        break
                    await asyncio.sleep(0.05)
        assert await hydra.token_is_active(tokens.access_token)

        installation = await PostgresInstallationIdentityReader(database).read()
        request: dict[str, object] = {
            "schemaVersion": 1,
            "mode": "resume-recovery-cleanup",
            "expectedInstallationId": str(installation.value),
            "operationId": str(uuid4()),
            "recoveryOperationId": original.operation_id,
            "operatorLabel": "Test host operator",
            "reason": "Corrected Hydra admin endpoint",
        }
        status, response = await run_maintenance(request, EXECUTION_DATABASE)
        assert status == 0 and response["outcome"] == "cleanup-authorized"
        assert await run_maintenance(request, EXECUTION_DATABASE) == (status, response)
        async with recovery_worker_process():
            finished = await _wait_for_release(database, alice.subject)
        assert finished.operation_id == original.operation_id
        assert not await hydra.token_is_active(tokens.access_token)
        assert await hydra.refresh_tokens(tokens) is None
        assert await run_maintenance(request, EXECUTION_DATABASE) == (status, response)
        async with database.session() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(HostMaintenanceReceiptRow)
                    .where(HostMaintenanceReceiptRow.recovery_operation_id == original.operation_id)
                )
                == 1
            )
            old_run = await session.get(IdentityRecoveryCleanupRunRow, failed.id)
            assert old_run is not None and old_run.terminal_reason == "permanent_provider_rejection"
            new_run = await session.scalar(
                select(IdentityRecoveryCleanupRunRow).where(
                    IdentityRecoveryCleanupRunRow.operation_id == original.operation_id,
                    IdentityRecoveryCleanupRunRow.id != failed.id,
                )
            )
            assert new_run is not None and new_run.terminal_reason == "cleanup_confirmed"
        assert (await recovery_browser.get("/sessions/whoami")).status_code == 200
        cookie = recovery_browser.cookies.get("ory_kratos_session")
        assert cookie is not None
        recovered = replace(
            alice, password=password.get_secret_value(), credential=BrowserSessionCredential(cookie)
        )
        fresh = await hydra.issue_tokens(recovered, browser=recovery_browser)
        assert await hydra.token_is_active(fresh.access_token)


@pytest.mark.asyncio
async def test_native_suspension_worker_preserves_original_across_protected_continuation() -> None:
    async with (
        asyncio.timeout(60),
        _database() as database,
        _api() as api,
        hydra_test_provider(kratos_public_url=EXECUTION_PUBLIC) as hydra,
        hydra_test_provider(
            client_id="inframeld-test-suspension-other", kratos_public_url=EXECUTION_PUBLIC
        ) as other,
        create_browser(public_url=EXECUTION_PUBLIC) as operator_browser,
        create_browser(public_url=EXECUTION_PUBLIC) as target_browser,
        create_browser(public_url=EXECUTION_PUBLIC) as late_browser,
        create_browser(public_url=HYDRA_PUBLIC_URL) as operator_login,
        create_browser(public_url=HYDRA_PUBLIC_URL) as target_login,
        create_browser(public_url=HYDRA_PUBLIC_URL) as other_login,
    ):
        operator = await register_human(operator_browser)
        target = await register_human(target_browser)
        async with database.session() as session, session.begin():
            actor = await MockAccessScenarios.seed_linked_human(
                session, VerifiedHumanIdentityDTO(AUTHORITY, operator.subject)
            )
            for action in (
                OrganizationAction.ADMIT_USERS,
                OrganizationAction.SUSPEND_USERS,
                OrganizationAction.RESTORE_USERS,
            ):
                session.add(
                    OrganizationActionGrantRow(
                        organization_id=actor.organization_id.value,
                        recipient_principal_id=actor.id.value,
                        action=action.value,
                        recipient_kind=actor.kind,
                        can_grant=True,
                    )
                )
            organization = await session.get(OrganizationRow, actor.organization_id.value)
            assert organization is not None
            revision = organization.access_revision

        actor_binding = await _binding(database, operator.subject)
        actor_tokens = await hydra.issue_tokens(
            operator, browser=operator_login, remember_login=True, credential_binding=actor_binding
        )
        actor_headers = {"Authorization": f"Bearer {actor_tokens.access_token.value}"}
        organization_path = f"/v1/organizations/{actor.organization_id.value}"
        admitted = await api.post(
            organization_path + "/human-admissions",
            headers=actor_headers | {"Idempotency-Key": str(uuid4())},
            json={"identityId": target.subject.value, "expectedAccessRevision": revision},
        )
        assert admitted.status_code == 201
        payload = TypeAdapter(dict[str, object]).validate_json(admitted.content, strict=True)
        principal_id = UUID(str(payload["principalId"]))
        admitted_revision = payload["accessRevision"]
        assert type(admitted_revision) is int and admitted_revision == revision + 1
        identity = VerifiedHumanIdentityDTO(AUTHORITY, target.subject)
        credential_reader = PostgresHumanCredentialStateReader(database)
        initial = await credential_reader.read(identity)
        assert (
            initial.version is not None and initial.installation_id == actor_binding.installation_id
        )
        binding = HumanOAuthCredentialBindingDTO(identity, initial.installation_id, initial.version)
        old_cli = await hydra.issue_tokens(
            target, browser=target_login, remember_login=True, credential_binding=binding
        )
        other_tokens = await other.issue_tokens(target, browser=other_login, remember_login=True)
        assert await hydra.login_can_skip(target_login) and await other.login_can_skip(other_login)
        assert await hydra.login_can_skip(operator_login)
        old_cookie = {"Cookie": f"ory_kratos_session={target.credential.value}"}
        old_bearer = {"Authorization": f"Bearer {old_cli.access_token.value}"}
        assert (await api.get("/v1/session", headers=old_cookie)).status_code == 200
        assert (await api.get("/v1/session", headers=old_bearer)).status_code == 200

        route = f"{organization_path}/humans/{principal_id}"
        suspend_headers = actor_headers | {"Idempotency-Key": str(uuid4())}
        suspend_body = {"expectedAccessRevision": admitted_revision, "reason": "Reviewed incident"}
        restore_headers = actor_headers | {"Idempotency-Key": str(uuid4())}
        restore_body = {
            "expectedAccessRevision": admitted_revision + 1,
            "securityReviewReference": "incident/42",
        }
        async with busy_application_job(database) as ordinary:
            accepted = await api.post(
                route + "/suspend", headers=suspend_headers, json=suspend_body
            )
            assert accepted.status_code == 202 and accepted.headers["cache-control"] == "no-store"
            original_response = TypeAdapter(dict[str, object]).validate_json(
                accepted.content, strict=True
            )
            original_id = UUID(str(original_response["cleanupOperationId"]))
            assert original_response["accessBlocked"] is True
            assert original_response["accessRevision"] == admitted_revision + 1
            replayed = await api.post(
                route + "/suspend", headers=suspend_headers, json=suspend_body
            )
            assert replayed.status_code == 202 and replayed.json() == original_response
            assert (await api.get("/v1/session", headers=old_cookie)).status_code == 403
            assert (await api.get("/v1/session", headers=old_bearer)).status_code == 403
            assert (
                await target_browser.get("/sessions/whoami", headers=old_cookie)
            ).status_code == 200
            assert await hydra.token_is_active(old_cli.access_token)
            premature = await api.post(
                route + "/restore", headers=restore_headers, json=restore_body
            )
            assert premature.status_code == 409

            async with recovery_worker_process(admin_url="http://127.0.0.1:1"):
                stopped, first = await _wait_for_suspension_status(
                    database, original_id, JobStatus.RECOVERY_REQUIRED
                )
            assert stopped.kratos_sessions is State.CONFIRMED
            assert stopped.hydra_cli_grants is State.UNCERTAIN
            assert stopped.hydra_remembered_logins is State.PENDING and stopped.completed_at is None
            assert first.attempt_count == 1 and first.pending_effect is not None
            assert first.pending_effect.startswith("hydra_cli_grants:1:")
            assert (
                await target_browser.get("/sessions/whoami", headers=old_cookie)
            ).status_code == 401
            assert await hydra.token_is_active(old_cli.access_token)
            assert await other.login_can_skip(other_login)

            late = await login_human(late_browser, target)
            late_cookie = {"Cookie": f"ory_kratos_session={late.value}"}
            assert (
                await late_browser.get("/sessions/whoami", headers=late_cookie)
            ).status_code == 200
            assert (await api.get("/v1/session", headers=late_cookie)).status_code == 403

            request: dict[str, object] = {
                "schemaVersion": 1,
                "mode": "human-suspension-cleanup",
                "expectedInstallationId": str(initial.installation_id.value),
                "operationId": str(uuid4()),
                "cleanupOperationId": str(original_id),
            }
            code, inspected = await run_maintenance(
                request | {"intent": "inspect"}, EXECUTION_DATABASE
            )
            assert code == 0 and inspected["execution"] == "stopped"
            assert inspected["steps"] == {
                "kratosSessions": "confirmed",
                "hydraCliGrants": "uncertain",
                "hydraRememberedLogins": "pending",
            }
            continuation = request | {
                "intent": "continue",
                "operatorLabel": "Native test operator",
                "reason": "Repeat the exact unconfirmed Hydra step",
            }
            code, receipt = await run_maintenance(continuation, EXECUTION_DATABASE)
            assert code == 0 and receipt["outcome"] == "requeued"
            assert await run_maintenance(continuation, EXECUTION_DATABASE) == (code, receipt)
            async with recovery_worker_process():
                completed, second = await _wait_for_suspension_status(
                    database, original_id, JobStatus.SUCCEEDED
                )
                async with database.session() as session, session.begin():
                    assert (
                        await PostgresJobStore(session).require_current(ordinary)
                    ).status is JobStatus.RUNNING
            assert second.id == first.id == stopped.job_id and second.attempt_count == 2
            assert (
                second.work_deadline == first.work_deadline
                and second.queued_deadline == first.queued_deadline
            )
            assert (
                completed.operation_id == stopped.operation_id
                and completed.completed_at is not None
            )
            assert (
                completed.kratos_sessions
                is completed.hydra_cli_grants
                is completed.hydra_remembered_logins
                is State.CONFIRMED
            )
            async with database.session() as session:
                authorization = await session.get(
                    HostMaintenanceReceiptRow,
                    (initial.installation_id.value, request["operationId"]),
                )
                earlier = await session.get(DurableJobAttemptRow, (first.id, 1))
                assert (
                    authorization is not None
                    and authorization.suspension_repeat_consumed_at is not None
                )
                assert authorization.suspension_obligation_id == original_id
                assert (
                    earlier is not None
                    and earlier.reason == "suspension_repeat:hydra_cli_grants:uncertain"
                )

        assert await run_maintenance(continuation, EXECUTION_DATABASE) == (code, receipt)
        assert not await hydra.token_is_active(old_cli.access_token)
        assert await hydra.refresh_tokens(old_cli) is None
        assert await other.token_is_active(other_tokens.access_token)
        assert await other.refresh_tokens(other_tokens) is not None
        assert not await hydra.login_can_skip(target_login) and not await other.login_can_skip(
            other_login
        )
        assert await hydra.login_can_skip(operator_login)
        assert (await api.get("/v1/session", headers=actor_headers)).status_code == 200
        assert (await operator_browser.get("/sessions/whoami")).status_code == 200
        # A newly created same-identity session survives because the first confirmed step is skipped.
        assert (await late_browser.get("/sessions/whoami", headers=late_cookie)).status_code == 200
        assert (await api.get("/v1/session", headers=late_cookie)).status_code == 403
        before_restore = await credential_reader.read(identity)
        assert before_restore.version == initial.version
        restored = await api.post(route + "/restore", headers=restore_headers, json=restore_body)
        assert restored.status_code == 200 and restored.headers["cache-control"] == "no-store"
        assert restored.json()["accessRevision"] == admitted_revision + 2
        restore_replay = await api.post(
            route + "/restore", headers=restore_headers, json=restore_body
        )
        assert restore_replay.status_code == 200 and restore_replay.json() == restored.json()
        current = await credential_reader.read(identity)
        assert current.version is not None and current.version.value == initial.version.value + 1
        assert (await api.get("/v1/session", headers=late_cookie)).status_code == 200
        assert (await api.get("/v1/session", headers=old_cookie)).status_code == 401
        assert (await api.get("/v1/session", headers=old_bearer)).status_code == 401
