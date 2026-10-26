"""Deliver real native hooks to the production private app and disposable database."""

import asyncio
import os
from collections.abc import AsyncGenerator
from urllib.parse import urlencode, urlsplit
from uuid import uuid4

import httpx2
import pytest
import pytest_asyncio
from pydantic import BaseModel, SecretStr
from sqlalchemy import func, select
from tests.support.integration_services import MAILPIT_URL
from tests.support.kratos_browser import (
    create_browser,
    login_human,
    read_browser_csrf_token,
    register_human,
    submit_password_login,
)
from tests.support.kratos_recovery import (
    redeem_recovery_code,
    request_recovery_code,
    wait_for_recovery_code,
)
from tests.support.kratos_settings import (
    SettingsFlowResponse,
    read_recovery_settings,
    submit_password_settings,
)
from tests.support.native_recovery_forwarder import NativeEvidenceObservation

from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState as State,
)
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_admission_row import (
    IdentityRecoveryAdmissionRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_cleanup_job_row import (
    IdentityRecoveryCleanupJobRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_cleanup_run_row import (
    IdentityRecoveryCleanupRunRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_evidence_receipt_row import (
    IdentityRecoveryEvidenceReceiptRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_session_binding_row import (
    IdentityRecoverySessionBindingRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_settings_binding_row import (
    IdentityRecoverySettingsBindingRow,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_KRATOS_INTEGRATION") != "1",
    reason="Requires native recovery qualification services",
)
PUBLIC = "http://kratos-recovery:4433"
PRIVATE = "http://recovery-callbacks:8081"
FORWARDER = "http://recovery-hooks:8080/internal/test/native-recovery"
KEY = "inframeld-native-recovery-hook-test-only"
HEADERS = {"X-Inframeld-Recovery-Key": KEY}


@pytest_asyncio.fixture
async def native_database() -> AsyncGenerator[Database]:
    database = Database(
        DatabaseSettings(
            host="recovery-postgres",
            name="recovery_delivery_test",
            user="recovery_test",
            password=SecretStr("recovery-test-only"),
        )
    )
    await database.startup()
    try:
        yield database
    finally:
        await database.shutdown()


async def _admission(database: Database, subject: str) -> IdentityRecoveryAdmissionRow:
    async with database.session() as session:
        return (
            await session.scalars(
                select(IdentityRecoveryAdmissionRow).where(
                    IdentityRecoveryAdmissionRow.subject == subject
                )
            )
        ).one()


async def _count_jobs(database: Database, subject: str) -> int:
    async with database.session() as session:
        return (
            await session.scalar(
                select(func.count())
                .select_from(IdentityRecoveryCleanupJobRow)
                .where(IdentityRecoveryCleanupJobRow.subject == subject)
            )
        ) or 0


class _Snapshot(BaseModel):
    received: list[NativeEvidenceObservation]
    statuses: list[int]


async def _snapshot(client: httpx2.AsyncClient, subject: str, phase: str) -> _Snapshot:
    response = await client.get(f"{FORWARDER}/observations/{subject}/{phase}", headers=HEADERS)
    assert response.status_code == 200
    return _Snapshot.model_validate_json(response.text)


@pytest.mark.asyncio
async def test_anonymous_email_request_has_no_recovery_effect(native_database: Database) -> None:
    async with (
        create_browser(public_url=PUBLIC) as owner,
        create_browser(public_url=PUBLIC) as browser,
    ):
        alice = await register_human(owner)
        await request_recovery_code(browser, alice.email)
        async with native_database.session() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(IdentityRecoveryAdmissionRow)
                    .where(IdentityRecoveryAdmissionRow.subject == alice.subject.value)
                )
                == 0
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(HumanCredentialVersionRow)
                    .where(HumanCredentialVersionRow.subject == alice.subject.value)
                )
                == 0
            )


@pytest.mark.asyncio
async def test_native_password_evidence_is_after_save_and_revocation_without_release(
    native_database: Database,
) -> None:
    async with (
        asyncio.timeout(30),
        create_browser(public_url=PUBLIC) as owner,
        create_browser(public_url=PUBLIC) as browser,
        create_browser(public_url=PUBLIC) as intervening,
        create_browser(public_url=PUBLIC) as bob_browser,
    ):
        alice = await register_human(owner)
        bob = await register_human(bob_browser)
        recovery = await request_recovery_code(browser, alice.email)
        response = await redeem_recovery_code(
            browser, recovery, await wait_for_recovery_code(alice.email)
        )
        settings = await read_recovery_settings(browser, response, public_url=PUBLIC)
        original = await _admission(native_database, alice.subject.value)
        assert original.flow_id == recovery.id
        assert (
            original.kratos_cleanup_state,
            original.hydra_cleanup_state,
            original.released_at,
        ) == (State.PENDING, State.PENDING, None)
        assert await _count_jobs(native_database, alice.subject.value) == 0
        await login_human(intervening, alice)
        password = SecretStr(f"Replacement-{uuid4().hex}!")
        saved = await submit_password_settings(browser, settings, password, public_url=PUBLIC)
        assert saved.status_code == 200, "Native password save did not finish."
        row = await _admission(native_database, alice.subject.value)
        assert row.operation_id == original.operation_id
        assert (row.kratos_cleanup_state, row.hydra_cleanup_state, row.released_at) == (
            State.CONFIRMED,
            State.PENDING,
            None,
        )
        assert await _count_jobs(native_database, alice.subject.value) == 1
        assert (await owner.get("/sessions/whoami")).status_code == 401
        assert (await intervening.get("/sessions/whoami")).status_code == 401
        assert (await browser.get("/sessions/whoami")).status_code == 200
        assert (await bob_browser.get("/sessions/whoami")).status_code == 200
        async with create_browser(public_url=PUBLIC) as login:
            assert (
                await submit_password_login(
                    login, email=alice.email, password=SecretStr(alice.password)
                )
            ).status_code == 400
            assert (
                await submit_password_login(login, email=alice.email, password=password)
            ).status_code == 200
        async with native_database.session() as session:
            assert (
                await session.scalar(
                    select(HumanCredentialVersionRow.version).where(
                        HumanCredentialVersionRow.subject == alice.subject.value
                    )
                )
                == 2
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(IdentityRecoveryAdmissionRow)
                    .where(IdentityRecoveryAdmissionRow.subject == bob.subject.value)
                )
                == 0
            )


@pytest.mark.asyncio
async def test_fresh_settings_in_bound_session_inherit_original_recovery(
    native_database: Database,
) -> None:
    async with (
        asyncio.timeout(30),
        create_browser(public_url=PUBLIC) as owner,
        create_browser(public_url=PUBLIC) as browser,
    ):
        alice = await register_human(owner)
        recovery = await request_recovery_code(browser, alice.email)
        first = await read_recovery_settings(
            browser,
            await redeem_recovery_code(
                browser, recovery, await wait_for_recovery_code(alice.email)
            ),
            public_url=PUBLIC,
        )
        started = await browser.get(
            "/self-service/settings/browser", headers={"Accept": "application/json"}
        )
        assert started.status_code == 200
        fresh = SettingsFlowResponse.model_validate_json(started.text)
        assert fresh.id != first.id
        saved = await submit_password_settings(
            browser, fresh, SecretStr(f"Replacement-{uuid4().hex}!"), public_url=PUBLIC
        )
        assert saved.status_code == 200
        async with native_database.session() as session:
            bindings = (
                await session.scalars(
                    select(IdentityRecoverySettingsBindingRow).where(
                        IdentityRecoverySettingsBindingRow.subject == alice.subject.value
                    )
                )
            ).all()
            receipts = (
                await session.scalars(
                    select(IdentityRecoveryEvidenceReceiptRow).where(
                        IdentityRecoveryEvidenceReceiptRow.subject == alice.subject.value,
                        IdentityRecoveryEvidenceReceiptRow.native_flow_id == fresh.id,
                    )
                )
            ).all()
            assert {row.event_type.value for row in receipts} == {
                "settings-flow-associated",
                "password-settings-saved",
            }
            assert all(row.source_recovery_flow_id is None for row in receipts)
            assert {first.id, fresh.id}.issubset({row.settings_flow_id for row in bindings})
            assert len(bindings) == 3  # Successful settings starts another native flow.
            assert len({row.operation_id for row in bindings}) == 1
            assert len({row.session_id for row in bindings}) == 1
            assert (
                next(
                    row for row in bindings if row.settings_flow_id == fresh.id
                ).source_recovery_flow_id
                is None
            )


@pytest.mark.asyncio
async def test_ordinary_settings_cannot_claim_recovery_from_browser_parameters(
    native_database: Database,
) -> None:
    async with asyncio.timeout(30), create_browser(public_url=PUBLIC) as owner:
        alice = await register_human(owner)
        started = await owner.get(
            "/self-service/settings/browser",
            params={"flow": str(uuid4()), "recovery_flow_id": str(uuid4())},
            headers={"Accept": "application/json"},
        )
        assert started.status_code == 200
        settings = SettingsFlowResponse.model_validate_json(started.text)
        saved = await submit_password_settings(
            owner, settings, SecretStr(f"Replacement-{uuid4().hex}!"), public_url=PUBLIC
        )
        assert saved.status_code == 200
        async with native_database.session() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(IdentityRecoveryAdmissionRow)
                    .where(IdentityRecoveryAdmissionRow.subject == alice.subject.value)
                )
                == 0
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(IdentityRecoveryEvidenceReceiptRow)
                    .where(IdentityRecoveryEvidenceReceiptRow.subject == alice.subject.value)
                )
                == 0
            )
        assert await _count_jobs(native_database, alice.subject.value) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("position", ["before", "after"])
async def test_lost_password_receipt_acknowledgment_preserves_original_progress(
    native_database: Database, position: str
) -> None:
    async with (
        asyncio.timeout(45),
        create_browser(public_url=PUBLIC) as owner,
        create_browser(public_url=PUBLIC) as browser,
        httpx2.AsyncClient(timeout=15, trust_env=False) as client,
    ):
        alice = await register_human(owner)
        recovery = await request_recovery_code(browser, alice.email)
        settings = await read_recovery_settings(
            browser,
            await redeem_recovery_code(
                browser, recovery, await wait_for_recovery_code(alice.email)
            ),
            public_url=PUBLIC,
        )
        control = f"{FORWARDER}/controls/{alice.subject.value}/password-saved"
        assert (
            await client.put(
                control, json={"position": position, "action": "fail"}, headers=HEADERS
            )
        ).status_code == 204
        try:
            password = SecretStr(f"Replacement-{uuid4().hex}!")
            await submit_password_settings(browser, settings, password, public_url=PUBLIC)
            row = await _admission(native_database, alice.subject.value)
            assert row.kratos_cleanup_state is (
                State.PENDING if position == "before" else State.CONFIRMED
            )
            assert await _count_jobs(native_database, alice.subject.value) == (
                0 if position == "before" else 1
            )
            assert row.released_at is None
            assert (await browser.get("/sessions/whoami")).status_code == 200
            async with create_browser(public_url=PUBLIC) as login:
                assert (
                    await submit_password_login(login, email=alice.email, password=password)
                ).status_code == 200
        finally:
            assert (await client.delete(control, headers=HEADERS)).status_code == 204
        snapshot = await _snapshot(client, alice.subject.value, "password-saved")
        received = snapshot.received
        assert received
        replay = await client.post(
            PRIVATE + "/internal/v2/identity-recovery/password-saved",
            json=received[0].model_dump(mode="json", by_alias=True, exclude_unset=True),
            headers=HEADERS,
        )
        assert replay.status_code == 202
        assert replay.json()["operationId"] == row.operation_id
        assert await _count_jobs(native_database, alice.subject.value) == 1
        async with native_database.session() as session:
            jobs = (
                await session.scalars(
                    select(IdentityRecoveryCleanupJobRow).where(
                        IdentityRecoveryCleanupJobRow.subject == alice.subject.value
                    )
                )
            ).all()
            run = (
                await session.scalars(
                    select(IdentityRecoveryCleanupRunRow).where(
                        IdentityRecoveryCleanupRunRow.operation_id == row.operation_id
                    )
                )
            ).one()
            assert len(jobs) == 1
            assert (run.max_attempts, run.consumed_attempts, run.ended_at) == (12, 0, None)


@pytest.mark.asyncio
async def test_private_process_has_no_public_docs_or_product_routes() -> None:
    async with httpx2.AsyncClient(base_url=PRIVATE, timeout=5, trust_env=False) as client:
        for path in ["/docs", "/redoc", "/openapi.json", "/v1/openapi.json", "/v1/session"]:
            response = await client.get(path)
            assert response.status_code == 404
            assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.asyncio
async def test_conflicting_body_flow_cannot_select_another_recovery(
    native_database: Database,
) -> None:
    from tests.support.kratos_browser import read_browser_csrf_token

    async with (
        asyncio.timeout(30),
        create_browser(public_url=PUBLIC) as owner,
        create_browser(public_url=PUBLIC) as browser,
    ):
        alice = await register_human(owner)
        recovery = await request_recovery_code(browser, alice.email)
        code = await wait_for_recovery_code(alice.email)
        forged = uuid4()
        redeemed = await browser.post(
            recovery.ui.action,
            data={
                "csrf_token": read_browser_csrf_token(recovery),
                "code": code.get_secret_value(),
                "method": "code",
                "flow": str(forged),
            },
            headers={"Accept": "text/html"},
        )
        settings = await read_recovery_settings(browser, redeemed, public_url=PUBLIC)
        admission = await _admission(native_database, alice.subject.value)
        assert admission.flow_id == recovery.id
        assert admission.flow_id != forged
        async with native_database.session() as session:
            binding = await session.get(
                IdentityRecoverySettingsBindingRow,
                (admission.installation_id, admission.authority, settings.id),
            )
            assert binding is not None
            assert binding.source_recovery_flow_id == recovery.id
        saved = await submit_password_settings(
            browser, settings, SecretStr(f"Replacement-{uuid4().hex}!"), public_url=PUBLIC
        )
        assert saved.status_code == 200
        async with native_database.session() as session:
            receipts = (
                await session.scalars(
                    select(IdentityRecoveryEvidenceReceiptRow).where(
                        IdentityRecoveryEvidenceReceiptRow.subject == alice.subject.value,
                        IdentityRecoveryEvidenceReceiptRow.native_flow_id == settings.id,
                    )
                )
            ).all()
            assert {row.event_type.value for row in receipts} == {
                "settings-flow-associated",
                "password-settings-saved",
            }
            assert all(row.source_recovery_flow_id == recovery.id for row in receipts)


@pytest.mark.asyncio
async def test_failed_admission_persistence_prevents_native_continuation(
    native_database: Database,
) -> None:
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import Connection, column

    async with (
        asyncio.timeout(30),
        create_browser(public_url=PUBLIC) as owner,
        create_browser(public_url=PUBLIC) as browser,
    ):
        alice = await register_human(owner)

        def reject(connection: Connection) -> None:
            Operations(MigrationContext.configure(connection)).create_check_constraint(
                "native_test_receipt_failure",
                "identity_recovery_evidence_receipts",
                column("subject") != alice.subject.value,
            )

        def restore(connection: Connection) -> None:
            Operations(MigrationContext.configure(connection)).drop_constraint(
                "native_test_receipt_failure", "identity_recovery_evidence_receipts", type_="check"
            )

        async with native_database.session() as session, session.begin():
            await (await session.connection()).run_sync(reject)
        try:
            recovery = await request_recovery_code(browser, alice.email)
            redeemed = await redeem_recovery_code(
                browser, recovery, await wait_for_recovery_code(alice.email)
            )
            assert redeemed.status_code == 303
            assert urlsplit(redeemed.headers["location"]).path == "/error", (
                "Failed admission must redirect to the error page, never password settings."
            )
            assert (await browser.get("/sessions/whoami")).status_code == 401
            async with native_database.session() as session:
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(IdentityRecoveryAdmissionRow)
                        .where(IdentityRecoveryAdmissionRow.subject == alice.subject.value)
                    )
                    == 0
                )
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(HumanCredentialVersionRow)
                        .where(HumanCredentialVersionRow.subject == alice.subject.value)
                    )
                    == 0
                )
        finally:
            async with native_database.session() as session, session.begin():
                await (await session.connection()).run_sync(restore)


@pytest.mark.asyncio
async def test_password_notification_waits_until_native_save_and_session_cleanup(
    native_database: Database,
) -> None:
    async with (
        asyncio.timeout(30),
        create_browser(public_url=PUBLIC) as owner,
        create_browser(public_url=PUBLIC) as browser,
        create_browser(public_url=PUBLIC) as intervening,
        httpx2.AsyncClient(timeout=12, trust_env=False) as client,
    ):
        alice = await register_human(owner)
        recovery = await request_recovery_code(browser, alice.email)
        settings = await read_recovery_settings(
            browser,
            await redeem_recovery_code(
                browser, recovery, await wait_for_recovery_code(alice.email)
            ),
            public_url=PUBLIC,
        )
        await login_human(intervening, alice)
        control = f"{FORWARDER}/controls/{alice.subject.value}/password-saved"
        assert (
            await client.put(
                control, json={"position": "before", "action": "pause"}, headers=HEADERS
            )
        ).status_code == 204
        password = SecretStr(f"Replacement-{uuid4().hex}!")
        task = asyncio.create_task(
            submit_password_settings(browser, settings, password, public_url=PUBLIC)
        )
        try:
            assert (await client.post(control + "/wait", headers=HEADERS)).status_code == 204
            assert not task.done()
            assert (await intervening.get("/sessions/whoami")).status_code == 401
            assert (await browser.get("/sessions/whoami")).status_code == 200
            async with create_browser(public_url=PUBLIC) as login:
                assert (
                    await submit_password_login(login, email=alice.email, password=password)
                ).status_code == 200
            assert (
                await _admission(native_database, alice.subject.value)
            ).kratos_cleanup_state is State.PENDING
            assert await _count_jobs(native_database, alice.subject.value) == 0
        finally:
            assert (await client.post(control + "/release", headers=HEADERS)).status_code == 204
            if not task.done():
                await asyncio.wait_for(task, 10)
            await client.delete(control, headers=HEADERS)
        assert (await task).status_code == 200
        assert (
            await _admission(native_database, alice.subject.value)
        ).kratos_cleanup_state is State.CONFIRMED


@pytest.mark.asyncio
async def test_lost_admission_acknowledgment_replays_without_another_version_change(
    native_database: Database,
) -> None:
    async with (
        asyncio.timeout(30),
        create_browser(public_url=PUBLIC) as owner,
        create_browser(public_url=PUBLIC) as browser,
        httpx2.AsyncClient(timeout=15, trust_env=False) as client,
    ):
        alice = await register_human(owner)
        control = f"{FORWARDER}/controls/{alice.subject.value}/admit"
        assert (
            await client.put(control, json={"position": "after", "action": "fail"}, headers=HEADERS)
        ).status_code == 204
        try:
            recovery = await request_recovery_code(browser, alice.email)
            response = await redeem_recovery_code(
                browser, recovery, await wait_for_recovery_code(alice.email)
            )
            assert response.status_code == 303
            assert urlsplit(response.headers["location"]).path == "/error"
        finally:
            assert (await client.delete(control, headers=HEADERS)).status_code == 204
        original = await _admission(native_database, alice.subject.value)
        snapshot = await _snapshot(client, alice.subject.value, "admit")
        assert snapshot.received and snapshot.statuses
        assert all(status == 202 for status in snapshot.statuses)
        replay = await client.post(
            PRIVATE + "/internal/v2/identity-recovery/admit",
            json=snapshot.received[0].model_dump(mode="json", by_alias=True, exclude_unset=True),
            headers=HEADERS,
        )
        assert replay.status_code == 202
        assert replay.headers["Cache-Control"] == "no-store"
        assert replay.json()["operationId"] == original.operation_id
        async with native_database.session() as session:
            assert (
                await session.scalar(
                    select(HumanCredentialVersionRow.version).where(
                        HumanCredentialVersionRow.subject == alice.subject.value
                    )
                )
                == 2
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(IdentityRecoveryEvidenceReceiptRow)
                    .where(IdentityRecoveryEvidenceReceiptRow.subject == alice.subject.value)
                )
                == 1
            )
        assert await _count_jobs(native_database, alice.subject.value) == 0
        assert original.released_at is None


class _RecoveryMailbox(BaseModel):
    messages_count: int


async def _recovery_mail_count(email: str) -> int:
    async with httpx2.AsyncClient(base_url=MAILPIT_URL, timeout=2, trust_env=False) as mailbox:
        response = await mailbox.get("/api/v1/search", params={"query": f"to:{email}"})
        assert response.status_code == 200, "Could not inspect recovery mail delivery."
        return _RecoveryMailbox.model_validate_json(response.text).messages_count


async def _wait_for_next_recovery_code(email: str, previous_count: int) -> SecretStr:
    """Wait for a new email rather than assuming two random codes must differ."""
    async with asyncio.timeout(20):
        while True:
            if await _recovery_mail_count(email) > previous_count:
                return await wait_for_recovery_code(email)
            await asyncio.sleep(0.25)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    [
        "%66low={selected}&flow={other}",
        "flow={selected}&%66low={other}",
        "flow={selected}&flow={other}",
        "flow={selected}&flow={selected}",
        "%66low={selected}",
        "%66%6c%6f%77={selected}",
        "flow={encoded}",
        "flow={selected}&broken",
        "flow={selected}&=ignored",
        "flow={selected}&un%72elated=ignored",
        "flow={selected}&flow=",
        "flow={selected}&flow",
    ],
)
async def test_noncanonical_native_source_cannot_bind_another_recovery(
    native_database: Database, query: str
) -> None:
    async with (
        asyncio.timeout(30),
        create_browser(public_url=PUBLIC) as owner,
        create_browser(public_url=PUBLIC) as older_browser,
        create_browser(public_url=PUBLIC) as current_browser,
    ):
        alice = await register_human(owner)
        older = await request_recovery_code(older_browser, alice.email)
        older_code = await wait_for_recovery_code(alice.email)
        older_settings = await read_recovery_settings(
            older_browser,
            await redeem_recovery_code(older_browser, older, older_code),
            public_url=PUBLIC,
        )
        original = await _admission(native_database, alice.subject.value)
        async with native_database.session() as session:
            binding = await session.get(
                IdentityRecoverySettingsBindingRow,
                (
                    original.installation_id,
                    original.authority,
                    older_settings.id,
                ),
            )
            assert binding is not None
            original_binding = (
                binding.operation_id,
                binding.session_id,
                binding.source_recovery_flow_id,
                binding.recorded_at,
            )

        previous_mail_count = await _recovery_mail_count(alice.email)
        selected = await request_recovery_code(current_browser, alice.email)
        selected_code = await _wait_for_next_recovery_code(alice.email, previous_mail_count)
        selected_id = str(selected.id)
        encoded = f"%{ord(selected_id[0]):02X}{selected_id[1:]}"
        source = query.format(selected=selected_id, other=older.id, encoded=encoded)
        action = urlsplit(selected.ui.action)
        response = await current_browser.post(
            f"{action.scheme}://{action.netloc}{action.path}?{source}",
            data={
                "csrf_token": read_browser_csrf_token(selected),
                "code": selected_code.get_secret_value(),
                "method": "code",
            },
            headers={"Accept": "text/html"},
        )

        async with native_database.session() as session:
            bindings = (
                await session.scalars(
                    select(IdentityRecoverySettingsBindingRow).where(
                        IdentityRecoverySettingsBindingRow.subject == alice.subject.value,
                    )
                )
            ).all()
            assert len(bindings) == 1, "A rejected source created another settings association."
            binding = bindings[0]
            assert binding.settings_flow_id == older_settings.id
            assert (
                binding.operation_id,
                binding.session_id,
                binding.source_recovery_flow_id,
                binding.recorded_at,
            ) == original_binding
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(IdentityRecoverySessionBindingRow)
                    .where(
                        IdentityRecoverySessionBindingRow.subject == alice.subject.value,
                    )
                )
                == 1
            )

            admissions = (
                await session.scalars(
                    select(IdentityRecoveryAdmissionRow).where(
                        IdentityRecoveryAdmissionRow.subject == alice.subject.value,
                    )
                )
            ).all()
            assert {row.flow_id for row in admissions} == {older.id, selected.id}
            assert (
                next(row for row in admissions if row.flow_id == older.id).operation_id
                == original.operation_id
            )
            assert all(
                (row.kratos_cleanup_state, row.hydra_cleanup_state, row.released_at)
                == (State.PENDING, State.PENDING, None)
                for row in admissions
            )
            receipts = (
                await session.scalars(
                    select(IdentityRecoveryEvidenceReceiptRow).where(
                        IdentityRecoveryEvidenceReceiptRow.subject == alice.subject.value,
                    )
                )
            ).all()
            assert {(row.event_type.value, row.native_flow_id) for row in receipts} == {
                ("recovery-code-verified", older.id),
                ("recovery-code-verified", selected.id),
                ("settings-flow-associated", older_settings.id),
            }
            assert (
                await session.scalar(
                    select(HumanCredentialVersionRow.version).where(
                        HumanCredentialVersionRow.subject == alice.subject.value,
                    )
                )
                == 3
            )
        assert await _count_jobs(native_database, alice.subject.value) == 0
        assert response.status_code == 303
        assert urlsplit(response.headers["location"]).path == "/error"


@pytest.mark.asyncio
async def test_canonical_native_source_allows_encoded_return_to_values(
    native_database: Database,
) -> None:
    async with (
        asyncio.timeout(30),
        create_browser(public_url=PUBLIC) as owner,
        create_browser(public_url=PUBLIC) as browser,
    ):
        alice = await register_human(owner)
        recovery = await request_recovery_code(browser, alice.email)
        action = urlsplit(recovery.ui.action)
        query = urlencode(
            {
                "flow": str(recovery.id),
                "return_to": f"{PUBLIC}/self-service/login/browser?from=recovery&next=login",
            }
        )
        redeemed = await browser.post(
            f"{action.scheme}://{action.netloc}{action.path}?{query}",
            data={
                "csrf_token": read_browser_csrf_token(recovery),
                "code": (await wait_for_recovery_code(alice.email)).get_secret_value(),
                "method": "code",
            },
            headers={"Accept": "text/html"},
        )
        settings = await read_recovery_settings(browser, redeemed, public_url=PUBLIC)
        saved = await submit_password_settings(
            browser, settings, SecretStr(f"Replacement-{uuid4().hex}!"), public_url=PUBLIC
        )
        assert saved.status_code == 200
        original = await _admission(native_database, alice.subject.value)
        assert original.flow_id == recovery.id
        assert (
            original.kratos_cleanup_state,
            original.hydra_cleanup_state,
            original.released_at,
        ) == (State.CONFIRMED, State.PENDING, None)
        async with native_database.session() as session:
            receipts = (
                await session.scalars(
                    select(IdentityRecoveryEvidenceReceiptRow).where(
                        IdentityRecoveryEvidenceReceiptRow.subject == alice.subject.value,
                        IdentityRecoveryEvidenceReceiptRow.native_flow_id == settings.id,
                    )
                )
            ).all()
            assert {row.event_type.value for row in receipts} == {
                "settings-flow-associated",
                "password-settings-saved",
            }
            assert all(row.source_recovery_flow_id == recovery.id for row in receipts)
            assert all(row.operation_id == original.operation_id for row in receipts)
            runs = (
                await session.scalars(
                    select(IdentityRecoveryCleanupRunRow).where(
                        IdentityRecoveryCleanupRunRow.operation_id == original.operation_id,
                    )
                )
            ).all()
            assert len(runs) == 1
            assert (runs[0].max_attempts, runs[0].consumed_attempts) == (12, 0)
        assert await _count_jobs(native_database, alice.subject.value) == 1
