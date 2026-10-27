"""Reject unsupported OAuth access before creating durable credential state."""

import os
from dataclasses import dataclass, replace
from typing import override

import httpx2
import pytest
from fastapi import FastAPI
from pydantic import HttpUrl
from sqlalchemy import func, select

from inframeld_backend.access.application.dtos.human_oauth_consent_request_dto import (
    HumanOAuthConsentRequestDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.oauth_consent_continuation_dto import (
    OAuthConsentContinuationDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.browser_session_verifier import (
    BrowserSessionVerifier,
)
from inframeld_backend.access.application.protocols.oauth_consent_decision_writer import (
    OAuthConsentDecisionWriter,
)
from inframeld_backend.access.application.protocols.oauth_consent_request_reader import (
    OAuthConsentRequestReader,
)
from inframeld_backend.access.application.services.human_oauth_consent_service import (
    HumanOAuthConsentService,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.application.value_objects.oauth_client_id import OAuthClientId
from inframeld_backend.access.application.value_objects.oauth_consent_challenge import (
    OAuthConsentChallenge,
)
from inframeld_backend.access.domain.enums.human_oauth_scope import HumanOAuthScope
from inframeld_backend.access.domain.value_objects.human_api_audience import HumanAPIAudience
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.routes.human_oauth_consent_routes import (
    create_human_oauth_consent_router,
)
from inframeld_backend.access.infrastructure.readers.postgres_human_credential_state_reader import (
    PostgresHumanCredentialStateReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_identity_recovery_block_reader import (
    PostgresIdentityRecoveryBlockReader,
)
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
)
from inframeld_backend.access.infrastructure.writers.postgres_human_credential_state_initializer import (
    PostgresHumanCredentialStateInitializer,
)
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers
from inframeld_backend.shared.infrastructure.resources.database import Database

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires PostgreSQL integration services",
)
AUDIENCE = HumanAPIAudience("https://api.example.test")
REQUEST = HumanOAuthConsentRequestDTO(
    IdentitySubject("alice"),
    OAuthClientId("inframeld-cli"),
    (HumanOAuthScope.API,),
    (AUDIENCE,),
    False,
)


@dataclass
class MockConsentRequestReader(OAuthConsentRequestReader):
    request: HumanOAuthConsentRequestDTO
    calls: list[str]

    @override
    async def read(
        self, challenge: OAuthConsentChallenge, *, timeout_seconds: float
    ) -> HumanOAuthConsentRequestDTO:
        self.calls.append("read")
        return self.request


@dataclass
class MockInvalidBrowserVerifier(BrowserSessionVerifier):
    calls: list[str]

    @override
    async def verify(self, credential: BrowserSessionCredential) -> VerifiedHumanIdentityDTO | None:
        self.calls.append("verify")
        return None


class MockUnexpectedConsentDecisionWriter(OAuthConsentDecisionWriter):
    @override
    async def allow(
        self,
        challenge: OAuthConsentChallenge,
        *,
        scopes: tuple[HumanOAuthScope, ...],
        audiences: tuple[HumanAPIAudience, ...],
        remember_for_seconds: int | None,
        binding: HumanOAuthCredentialBindingDTO,
        timeout_seconds: float,
    ) -> OAuthConsentContinuationDTO:
        raise AssertionError("Unsupported access must not reach Hydra approval.")

    @override
    async def deny(
        self, challenge: OAuthConsentChallenge, *, timeout_seconds: float
    ) -> OAuthConsentContinuationDTO:
        raise AssertionError("Unsupported access must not submit a Hydra decision.")


@pytest.mark.asyncio
@pytest.mark.parametrize("unsupported", ["client", "scope", "audience"])
async def test_unsupported_approval_creates_no_credential_version(
    database: Database, unsupported: str
) -> None:
    """An invalid cookie cannot turn an unsupported request into a metadata write."""
    if unsupported == "client":
        request = replace(REQUEST, client_id=OAuthClientId("another-client"))
    elif unsupported == "scope":
        request = replace(REQUEST, scopes=(HumanOAuthScope.OPENID,))
    else:
        request = replace(REQUEST, audiences=(HumanAPIAudience("https://other.test"),))
    calls: list[str] = []
    service = HumanOAuthConsentService(
        MockConsentRequestReader(request, calls),
        MockUnexpectedConsentDecisionWriter(),
        MockInvalidBrowserVerifier(calls),
        PostgresIdentityRecoveryBlockReader(database),
        credential_states=PostgresHumanCredentialStateReader(database),
        credential_initializer=PostgresHumanCredentialStateInitializer(database),
        authority=IdentityAuthority("kratos:test"),
        api_audience=AUDIENCE,
    )
    application = FastAPI()
    register_error_handlers(application)
    application.include_router(
        create_human_oauth_consent_router(
            service, CSRFProtectionDependency((HttpUrl("https://account.test"),))
        )
    )
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=application), base_url=AUDIENCE.value
    ) as client:
        response = await client.post(
            "/v1/oauth/consent",
            json={"consentChallenge": "private-challenge", "decision": "allow"},
            headers={
                "Cookie": "ory_kratos_session=invalid-cookie",
                "Origin": "https://account.test",
                "X-Inframeld-CSRF": "1",
            },
        )
    async with database.session() as session:
        assert (
            await session.scalar(select(func.count()).select_from(HumanCredentialVersionRow)) == 0
        )
    assert response.status_code == 403, response.text
    assert response.json()["code"] == "access_denied"
    assert response.headers["Cache-Control"] == "no-store"
    assert calls == ["read"]
