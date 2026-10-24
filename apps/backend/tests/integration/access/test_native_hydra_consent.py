"""Exercise native Kratos login followed by the production consent API."""

import asyncio
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx2
import pytest
from pydantic import BaseModel, ConfigDict, HttpUrl
from sqlalchemy import func, select
from tests.support.access_scenarios import MockAccessScenarios
from tests.support.hydra_provider import (
    API_AUDIENCE,
    HYDRA_ISSUER,
    HydraTestProvider,
    PendingHydraConsentDTO,
    hydra_test_provider,
)
from tests.support.integration_services import (
    HYDRA_ADMIN_URL,
    HYDRA_PUBLIC_URL,
    KRATOS_ADMIN_URL,
    KRATOS_PUBLIC_URL,
)
from tests.support.kratos_admin import disable_identity
from tests.support.kratos_browser import RegisteredHumanDTO, create_browser, register_human

from inframeld_backend.access.application.dtos.identity_recovery_event_dto import (
    IdentityRecoveryEventDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.identity_recovery_event_kind import (
    IdentityRecoveryEventKind,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_recovery_flow_id import (
    IdentityRecoveryFlowId,
)
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.settings.csrf_settings import CSRFSettings
from inframeld_backend.access.infrastructure.settings.hydra_settings import HydraSettings
from inframeld_backend.access.infrastructure.settings.kratos_settings import KratosSettings
from inframeld_backend.access.infrastructure.writers.postgres_identity_recovery_admission_writer import (
    PostgresIdentityRecoveryAdmissionWriter,
)
from inframeld_backend.bootstrap.application_factory import create_app
from inframeld_backend.bootstrap.application_settings import get_settings
from inframeld_backend.shared.infrastructure.readers.postgres_installation_identity_reader import (
    PostgresInstallationIdentityReader,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_HYDRA_INTEGRATION") != "1",
    reason="Requires the private integration services",
)
AUTHORITY = IdentityAuthority("kratos:test")
UI_ORIGIN = "http://hydra-test-ui.invalid"


@dataclass
class NativeConsentScenarioDTO:
    provider: HydraTestProvider
    api: httpx2.AsyncClient
    browser: httpx2.AsyncClient
    alice: RegisteredHumanDTO
    database: Database

    def headers(self) -> dict[str, str]:
        cookie = self.browser.cookies.get("ory_kratos_session")
        assert cookie is not None
        return {
            "Cookie": f"ory_kratos_session={cookie}",
            "Origin": UI_ORIGIN,
            "X-Inframeld-CSRF": "1",
        }

    async def begin(self) -> PendingHydraConsentDTO:
        return await self.provider.begin_native_consent(self.alice, browser=self.browser)

    async def decide(
        self, pending: PendingHydraConsentDTO, *, remember: bool = False, decision: str = "allow"
    ) -> httpx2.Response:
        return await self.api.post(
            "/v1/oauth/consent",
            json={
                "consentChallenge": pending.challenge.get_secret_value(),
                "decision": decision,
                "remember": remember,
            },
            headers=self.headers(),
        )

    async def inspect(self, pending: PendingHydraConsentDTO) -> httpx2.Response:
        return await self.api.get(
            "/v1/oauth/consent",
            params={"consent_challenge": pending.challenge.get_secret_value()},
            headers=self.headers(),
        )

    async def admit_recovery(self) -> IdentityRecoveryEventDTO:
        installation_id = await PostgresInstallationIdentityReader(self.database).read()
        event = IdentityRecoveryEventDTO(
            IdentityRecoveryFlowId(uuid4()),
            VerifiedHumanIdentityDTO(AUTHORITY, self.alice.subject),
            IdentityRecoveryEventKind.RECOVERY,
        )
        async with self.database.session() as session, session.begin():
            await PostgresIdentityRecoveryAdmissionWriter(
                session,
                installation_id=installation_id,
                authority=AUTHORITY,
            ).reserve(event)
        return event


@asynccontextmanager
async def native_consent_scenario(
    database: Database, settings: DatabaseSettings
) -> AsyncGenerator[NativeConsentScenarioDTO]:
    configured = get_settings().model_copy(
        update={
            "database": settings,
            "kratos": KratosSettings(
                public_url=HttpUrl(KRATOS_PUBLIC_URL),
                admin_url=HttpUrl(KRATOS_ADMIN_URL),
                authority=AUTHORITY,
            ),
            "hydra": HydraSettings(
                admin_url=HttpUrl(HYDRA_ADMIN_URL),
                public_url=HttpUrl(HYDRA_PUBLIC_URL),
                issuer=HYDRA_ISSUER,
                api_audience=API_AUDIENCE,
            ),
            "csrf": CSRFSettings(trusted_origins=(HttpUrl(UI_ORIGIN),)),
        }
    )
    application = create_app(configured)
    async with (
        asyncio.timeout(30.0),
        application.router.lifespan_context(application),
        hydra_test_provider() as provider,
        create_browser() as browser,
        httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=application),
            base_url=API_AUDIENCE.value,
            timeout=5.0,
        ) as api,
    ):
        alice = await register_human(browser)
        yield NativeConsentScenarioDTO(provider, api, browser, alice, database)


@pytest.mark.asyncio
async def test_native_login_and_consent_do_not_provision_a_local_account(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    """Alice can complete OAuth before admission, but cannot access the product yet."""
    async with native_consent_scenario(database, temporary_postgres_settings) as scenario:
        pending = await scenario.begin()
        inspected = await scenario.inspect(pending)
        assert inspected.status_code == 200
        assert inspected.json()["accountSubject"] == scenario.alice.subject.value
        assert inspected.json()["approvalRequired"]
        assert inspected.json()["rememberConsentSeconds"] == 3600
        decision = await scenario.decide(pending)
        assert decision.status_code == 200
        code = await scenario.provider.finish_native_consent(
            pending, decision.json()["redirectTo"], browser=scenario.browser
        )
        tokens = await scenario.provider.exchange_authorization_code(code)
        assert tokens is not None
        assert await scenario.provider.token_is_active(tokens.access_token)
        refreshed = await scenario.provider.refresh_tokens(tokens)
        assert refreshed is not None
        response = await scenario.api.get(
            "/v1/session", headers={"Authorization": f"Bearer {refreshed.access_token.value}"}
        )
        assert response.status_code == 403
        async with database.session() as session:
            assert await session.scalar(select(func.count()).select_from(PrincipalRow)) == 0


@pytest.mark.asyncio
async def test_native_remembered_consent_uses_one_hour_and_keeps_the_original_approval(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    async with native_consent_scenario(database, temporary_postgres_settings) as scenario:
        first = await scenario.begin()
        decision = await scenario.decide(first, remember=True)
        assert decision.status_code == 200
        code = await scenario.provider.finish_native_consent(
            first, decision.json()["redirectTo"], browser=scenario.browser
        )
        tokens = await scenario.provider.exchange_authorization_code(code)
        assert tokens is not None
        async with httpx2.AsyncClient(timeout=5.0, trust_env=False) as admin:
            sessions = await admin.get(
                f"{HYDRA_ADMIN_URL}/admin/oauth2/auth/sessions/consent",
                params={"subject": scenario.alice.subject.value},
            )
        assert sessions.status_code == 200
        original = sessions.json()
        assert len(original) == 1
        assert original[0]["remember"] is True
        assert original[0]["remember_for"] == 3600
        assert await scenario.provider.login_can_skip(scenario.browser)
        second = await scenario.begin()
        assert second.consent_skipped
        inspected = await scenario.inspect(second)
        assert inspected.status_code == 200
        assert not inspected.json()["approvalRequired"]
        decision = await scenario.decide(second, remember=True)
        assert decision.status_code == 200
        code = await scenario.provider.finish_native_consent(
            second, decision.json()["redirectTo"], browser=scenario.browser
        )
        assert await scenario.provider.exchange_authorization_code(code) is not None
        async with httpx2.AsyncClient(timeout=5.0, trust_env=False) as admin:
            sessions = await admin.get(
                f"{HYDRA_ADMIN_URL}/admin/oauth2/auth/sessions/consent",
                params={"subject": scenario.alice.subject.value},
            )
        assert sessions.json() == original


@pytest.mark.asyncio
async def test_declining_consent_returns_an_oauth_denial_without_tokens(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    async with native_consent_scenario(database, temporary_postgres_settings) as scenario:
        pending = await scenario.begin()
        decision = await scenario.decide(pending, decision="deny")
        assert decision.status_code == 200
        response = await scenario.browser.get(decision.json()["redirectTo"])
        assert response.status_code in {302, 303}
        query = parse_qs(urlsplit(response.headers["location"]).query)
        assert query["error"] == ["access_denied"]
        assert "code" not in query
        assert query["state"] == [pending.state.get_secret_value()]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change,expected",
    [
        ("recovery", 403),
        ("revoked_session", 401),
        ("disabled_identity", 401),
        ("different_browser", 403),
    ],
)
async def test_approval_rechecks_the_browser_and_recovery_after_inspection(
    database: Database, temporary_postgres_settings: DatabaseSettings, change: str, expected: int
) -> None:
    async with native_consent_scenario(database, temporary_postgres_settings) as scenario:
        pending = await scenario.begin()
        assert (await scenario.inspect(pending)).status_code == 200
        if change == "recovery":
            await scenario.admit_recovery()
        elif change == "revoked_session":
            async with httpx2.AsyncClient(timeout=5.0, trust_env=False) as admin:
                response = await admin.delete(
                    f"{KRATOS_ADMIN_URL}/admin/identities/{scenario.alice.subject.value}/sessions"
                )
                assert response.status_code == 204
        elif change == "disabled_identity":
            await disable_identity(scenario.alice.subject)
        else:
            async with create_browser() as other:
                bob = await register_human(other)
            response = await scenario.api.post(
                "/v1/oauth/consent",
                json={
                    "consentChallenge": pending.challenge.get_secret_value(),
                    "decision": "allow",
                },
                headers={
                    "Cookie": f"ory_kratos_session={bob.credential.value}",
                    "Origin": UI_ORIGIN,
                    "X-Inframeld-CSRF": "1",
                },
            )
            assert response.status_code == expected
            return
        assert (await scenario.decide(pending)).status_code == expected


@pytest.mark.asyncio
async def test_remembered_consent_cannot_bypass_a_new_recovery_block(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    async with native_consent_scenario(database, temporary_postgres_settings) as scenario:
        first = await scenario.begin()
        decision = await scenario.decide(first, remember=True)
        code = await scenario.provider.finish_native_consent(
            first, decision.json()["redirectTo"], browser=scenario.browser
        )
        assert await scenario.provider.exchange_authorization_code(code) is not None
        second = await scenario.begin()
        assert second.consent_skipped
        await scenario.admit_recovery()
        assert (await scenario.decide(second)).status_code == 403


@pytest.mark.asyncio
async def test_delayed_approval_between_bulk_calls_cannot_bypass_recovery_block(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    """A late grant and its refresh remain unusable after the local recovery block is released."""
    from threading import Event
    from unittest.mock import patch

    from ory_hydra_client import ApiClient, Configuration, OAuth2Api
    from ory_hydra_client.models.accept_o_auth2_consent_request import AcceptOAuth2ConsentRequest
    from ory_hydra_client.models.o_auth2_redirect_to import OAuth2RedirectTo

    from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
        IdentityRecoveryCleanupState,
    )
    from inframeld_backend.access.infrastructure.revokers.hydra_human_oauth_credential_revoker import (
        HydraHumanOAuthCredentialRevoker,
    )

    async with native_consent_scenario(database, temporary_postgres_settings) as scenario:
        async with database.session() as session, session.begin():
            await MockAccessScenarios.seed_linked_human(
                session, VerifiedHumanIdentityDTO(AUTHORITY, scenario.alice.subject)
            )
        pending = await scenario.begin()
        arrived = asyncio.Event()
        release = Event()
        loop = asyncio.get_running_loop()
        original = OAuth2Api.accept_o_auth2_consent_request
        sdk = ApiClient(Configuration(host=HYDRA_ADMIN_URL, retries=0, debug=False))

        def mock_paused_accept(
            self: OAuth2Api,
            consent_challenge: str,
            accept_o_auth2_consent_request: AcceptOAuth2ConsentRequest | None = None,
            _request_timeout: float | None = None,
        ) -> OAuth2RedirectTo:
            assert consent_challenge == pending.challenge.get_secret_value()
            loop.call_soon_threadsafe(arrived.set)
            assert release.wait(3.0), "Delayed approval was not released."
            return original(
                self,
                consent_challenge=consent_challenge,
                accept_o_auth2_consent_request=accept_o_auth2_consent_request,
                _request_timeout=_request_timeout,
            )

        try:
            with patch.object(OAuth2Api, "accept_o_auth2_consent_request", new=mock_paused_accept):
                async with asyncio.TaskGroup() as tasks:
                    approval = tasks.create_task(scenario.decide(pending))
                    await arrived.wait()
                    event = await scenario.admit_recovery()
                    async with httpx2.AsyncClient(timeout=5.0, trust_env=False) as admin:
                        response = await admin.delete(
                            f"{KRATOS_ADMIN_URL}/admin/identities/{scenario.alice.subject.value}/sessions"
                        )
                    assert response.status_code == 204
                    revoker = HydraHumanOAuthCredentialRevoker(OAuth2Api(sdk))
                    assert (
                        await revoker.revoke_cli_grants(scenario.alice.subject, timeout_seconds=3.0)
                        == IdentityRecoveryCleanupState.CONFIRMED
                    )
                    release.set()
                decision = approval.result()
                assert decision.status_code == 200
            code = await scenario.provider.finish_native_consent(
                pending, decision.json()["redirectTo"], browser=scenario.browser
            )
            tokens = await scenario.provider.exchange_authorization_code(code)
            assert tokens is not None
            assert await scenario.provider.token_is_active(tokens.access_token)
            assert (
                await revoker.revoke_remembered_logins(scenario.alice.subject, timeout_seconds=3.0)
                == IdentityRecoveryCleanupState.CONFIRMED
            )
            assert await scenario.provider.token_is_active(tokens.access_token)
            response = await scenario.api.get(
                "/v1/session", headers={"Authorization": f"Bearer {tokens.access_token.value}"}
            )
            assert response.status_code == 401
            assert response.json()["code"] == "http_error"
            assert 'error="invalid_token"' in response.headers["www-authenticate"]
            # Only the local test invokes completion with trusted outcomes. No
            # production hook or password-reset association is established here.
            await _record_test_cleanup(scenario.database, event)
            released = await scenario.api.get(
                "/v1/session", headers={"Authorization": f"Bearer {tokens.access_token.value}"}
            )
            assert released.status_code == 401
            assert await scenario.provider.token_is_active(tokens.access_token)
            refreshed = await scenario.provider.refresh_tokens(tokens)
            assert refreshed is not None
            assert await scenario.provider.token_is_active(refreshed.access_token)
            assert (
                await scenario.api.get(
                    "/v1/session",
                    headers={"Authorization": f"Bearer {refreshed.access_token.value}"},
                )
            ).status_code == 401
            async with httpx2.AsyncClient(timeout=5.0, trust_env=False) as observer:
                introspected = await observer.post(
                    f"{HYDRA_ADMIN_URL}/admin/oauth2/introspect",
                    data={"token": refreshed.access_token.value},
                )
                assert introspected.status_code == 200
                observation = _VersionedTokenObservation.model_validate_json(introspected.content)
                assert observation.active
                assert observation.ext.inframeld_credential_version == 1
                userinfo = await observer.get(
                    f"{HYDRA_PUBLIC_URL}/userinfo",
                    headers={"Authorization": f"Bearer {refreshed.access_token.value}"},
                )
                assert userinfo.status_code == 200
                assert (
                    _UserInfoObservation.model_validate_json(userinfo.content).sub
                    == scenario.alice.subject.value
                )
            async with create_browser() as fresh_browser:
                pending_fresh = await scenario.provider.begin_native_consent(
                    scenario.alice, browser=fresh_browser
                )
                cookie = fresh_browser.cookies.get("ory_kratos_session")
                assert cookie is not None
                fresh_decision = await scenario.api.post(
                    "/v1/oauth/consent",
                    json={
                        "consentChallenge": pending_fresh.challenge.get_secret_value(),
                        "decision": "allow",
                    },
                    headers={
                        "Cookie": f"ory_kratos_session={cookie}",
                        "Origin": UI_ORIGIN,
                        "X-Inframeld-CSRF": "1",
                    },
                )
                assert fresh_decision.status_code == 200
                fresh_code = await scenario.provider.finish_native_consent(
                    pending_fresh, fresh_decision.json()["redirectTo"], browser=fresh_browser
                )
                fresh_tokens = await scenario.provider.exchange_authorization_code(fresh_code)
                assert fresh_tokens is not None
                assert (
                    await scenario.api.get(
                        "/v1/session",
                        headers={"Authorization": f"Bearer {fresh_tokens.access_token.value}"},
                    )
                ).status_code == 200
                assert (
                    await scenario.api.get(
                        "/v1/session",
                        headers={"Authorization": f"Bearer {refreshed.access_token.value}"},
                    )
                ).status_code == 401
        finally:
            release.set()
            sdk.rest_client.pool_manager.clear()


@pytest.mark.asyncio
async def test_approved_continuation_after_both_bulk_calls_is_rejected_by_pinned_hydra(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    """Record the stale-cookie denial, without treating it as a universal issuance fence."""
    from ory_hydra_client import ApiClient, Configuration, OAuth2Api

    from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
        IdentityRecoveryCleanupState,
    )
    from inframeld_backend.access.infrastructure.revokers.hydra_human_oauth_credential_revoker import (
        HydraHumanOAuthCredentialRevoker,
    )

    async with native_consent_scenario(database, temporary_postgres_settings) as scenario:
        pending = await scenario.begin()
        decision = await scenario.decide(pending)
        assert decision.status_code == 200
        await scenario.admit_recovery()
        async with httpx2.AsyncClient(timeout=5.0, trust_env=False) as admin:
            response = await admin.delete(
                f"{KRATOS_ADMIN_URL}/admin/identities/{scenario.alice.subject.value}/sessions"
            )
        assert response.status_code == 204
        sdk = ApiClient(Configuration(host=HYDRA_ADMIN_URL, retries=0, debug=False))
        try:
            revoker = HydraHumanOAuthCredentialRevoker(OAuth2Api(sdk))
            assert (
                await revoker.revoke_cli_grants(scenario.alice.subject, timeout_seconds=3.0)
                == IdentityRecoveryCleanupState.CONFIRMED
            )
            assert (
                await revoker.revoke_remembered_logins(scenario.alice.subject, timeout_seconds=3.0)
                == IdentityRecoveryCleanupState.CONFIRMED
            )
        finally:
            sdk.rest_client.pool_manager.clear()
        resumed = await scenario.browser.get(decision.json()["redirectTo"])
        assert resumed.status_code in {302, 303}
        query = parse_qs(urlsplit(resumed.headers["location"]).query)
        assert query["error"] == ["error"]
        assert "code" not in query
        assert query["state"] == [pending.state.get_secret_value()]


@pytest.mark.asyncio
async def test_native_login_can_authenticate_again_after_the_old_session_is_revoked(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    """The browser can use credentials again without needing a still-valid old cookie."""
    async with native_consent_scenario(database, temporary_postgres_settings) as scenario:
        async with httpx2.AsyncClient(timeout=5.0, trust_env=False) as admin:
            response = await admin.delete(
                f"{KRATOS_ADMIN_URL}/admin/identities/{scenario.alice.subject.value}/sessions"
            )
        assert response.status_code == 204
        pending = await scenario.begin()
        assert (await scenario.inspect(pending)).status_code == 200
        decision = await scenario.decide(pending)
        assert decision.status_code == 200
        code = await scenario.provider.finish_native_consent(
            pending, decision.json()["redirectTo"], browser=scenario.browser
        )
        tokens = await scenario.provider.exchange_authorization_code(code)
        assert tokens is not None
        assert await scenario.provider.token_is_active(tokens.access_token)


class _VersionClaims(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True, strict=True)
    inframeld_installation_id: str
    inframeld_credential_version: int


class _VersionedTokenObservation(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True, strict=True)
    active: bool
    ext: _VersionClaims


class _UserInfoObservation(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True, strict=True)
    sub: str


async def _record_test_cleanup(database: Database, event: IdentityRecoveryEventDTO) -> None:
    from inframeld_backend.access.application.services.identity_recovery_completion_service import (
        IdentityRecoveryCompletionService,
    )
    from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
        IdentityRecoveryCleanupState,
    )
    from inframeld_backend.access.infrastructure.readers.postgres_identity_recovery_completion_facts_reader import (
        PostgresIdentityRecoveryCompletionFactsReader,
    )
    from inframeld_backend.access.infrastructure.repositories.postgres_identity_recovery_repository import (
        PostgresIdentityRecoveryRepository,
    )
    from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
        SqlAlchemyTransactionManager,
    )

    installation_id = await PostgresInstallationIdentityReader(database).read()
    async with database.session() as session:
        service = IdentityRecoveryCompletionService(
            SqlAlchemyTransactionManager(session),
            PostgresIdentityRecoveryCompletionFactsReader(session),
            PostgresIdentityRecoveryRepository(session),
            installation_id=installation_id,
            authority=AUTHORITY,
        )
        result = await service.record_cleanup(
            event=event,
            kratos_outcome=IdentityRecoveryCleanupState.CONFIRMED,
            hydra_outcome=IdentityRecoveryCleanupState.CONFIRMED,
        )
    assert result.released_at is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("initially_blocked", [False, True])
async def test_browser_verification_cannot_cross_recovery_completion(
    database: Database, temporary_postgres_settings: DatabaseSettings, initially_blocked: bool
) -> None:
    """A verified browser result cannot inherit a new version or outlive its observed block."""
    from unittest.mock import patch

    from inframeld_backend.access.application.value_objects.browser_session_credential import (
        BrowserSessionCredential,
    )
    from inframeld_backend.access.infrastructure.verifiers.kratos_browser_session_verifier import (
        KratosBrowserSessionVerifier,
    )

    async with native_consent_scenario(database, temporary_postgres_settings) as scenario:
        pending = await scenario.begin()
        event = await scenario.admit_recovery() if initially_blocked else None
        arrived = asyncio.Event()
        release = asyncio.Event()
        original = KratosBrowserSessionVerifier.verify

        async def paused(
            self: KratosBrowserSessionVerifier, credential: BrowserSessionCredential
        ) -> VerifiedHumanIdentityDTO | None:
            identity = await original(self, credential)
            arrived.set()
            async with asyncio.timeout(5):
                await release.wait()
            return identity

        with patch.object(KratosBrowserSessionVerifier, "verify", new=paused):
            approval = asyncio.create_task(scenario.decide(pending))
            try:
                async with asyncio.timeout(3):
                    await arrived.wait()
                if event is None:
                    event = await scenario.admit_recovery()
                # Test-controlled outcomes isolate state ordering, not provider cleanup.
                await _record_test_cleanup(database, event)
                release.set()
                response = await approval
                assert response.status_code == 403
                assert response.json()["code"] == "access_denied"
            finally:
                release.set()
                if not approval.done():
                    approval.cancel()
                await asyncio.gather(approval, return_exceptions=True)
