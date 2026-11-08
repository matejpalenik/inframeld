"""Keep password enrollment separate from current login and local admission."""

import asyncio
import http.client
import json
import traceback
from datetime import UTC, datetime, timedelta
from json import JSONDecodeError
from unittest.mock import patch
from uuid import UUID

import httpx2
import pytest
from ory_kratos_client.api.frontend_api import FrontendApi
from ory_kratos_client.api.identity_api import IdentityApi
from ory_kratos_client.api_client import ApiClient
from ory_kratos_client.configuration import Configuration
from ory_kratos_client.exceptions import (
    ApiException,
    ForbiddenException,
    NotFoundException,
    OpenApiException,
    UnauthorizedException,
)
from ory_kratos_client.models.identity import Identity
from ory_kratos_client.models.identity_credentials import IdentityCredentials
from ory_kratos_client.models.session import Session
from ory_kratos_client.models.session_authentication_method import SessionAuthenticationMethod
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from urllib3.exceptions import HTTPError

from inframeld_backend.access.application.dtos.invitation_browser_proof_dto import (
    InvitationBrowserProofDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.infrastructure.verifiers.kratos_invitation_session_verifier import (
    KratosInvitationSessionVerifier,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)

AUTHORITY = IdentityAuthority("kratos:test")
IDENTITY_ID = UUID(int=1)
IDENTITY = VerifiedHumanIdentityDTO(authority=AUTHORITY, subject=IdentitySubject(str(IDENTITY_ID)))
COOKIE = BrowserSessionCredential("invitation-test-session")


def _frontend() -> FrontendApi:
    return FrontendApi(ApiClient(Configuration(host="http://kratos.test")))


def _admin() -> IdentityApi:
    return IdentityApi(ApiClient(Configuration(host="http://kratos-admin.test")))


def _identity(*, password: bool = True) -> Identity:
    return Identity(
        id=IDENTITY_ID,
        schema_id="default",
        schema_url="http://kratos.test/schemas/default",
        state="active",
        traits={"email": "recipient@example.test"},
        credentials={
            "password": IdentityCredentials(
                type="password",
                config={"hashed_password": "synthetic-verifier"} if password else {},
            )
        },
    )


def _session(*, method: str = "oidc") -> Session:
    return Session(
        id=UUID(int=2),
        active=True,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        identity=_identity(password=False),
        authentication_methods=[
            SessionAuthenticationMethod(method=method, completed_at=datetime.now(UTC))
        ],
    )


@pytest.mark.asyncio
async def test_oidc_session_for_password_enrolled_identity_has_completion() -> None:
    """Prior password onboarding must not demand password reauthentication now."""
    frontend, admin = _frontend(), _admin()

    with (
        patch.object(frontend, "to_session", return_value=_session()),
        patch.object(admin, "get_identity", return_value=_identity()) as get_identity,
    ):
        proof = await KratosInvitationSessionVerifier(
            frontend, AUTHORITY, identity_client=admin
        ).verify(COOKIE, observe_password_completion=True)

    assert proof == InvitationBrowserProofDTO(identity=IDENTITY, password_completed=True)
    assert get_identity.call_args.kwargs.keys() == {"id", "include_credential", "_request_timeout"}
    assert get_identity.call_args.kwargs["id"] == str(IDENTITY_ID)
    assert get_identity.call_args.kwargs["include_credential"] == ["password"]
    assert 0 < get_identity.call_args.kwargs["_request_timeout"] <= 5.0


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["password", "oidc"])
async def test_preview_observes_identity_without_admin_or_enrollment(method: str) -> None:
    frontend, admin = _frontend(), _admin()

    with (
        patch.object(frontend, "to_session", return_value=_session(method=method)),
        patch.object(admin, "get_identity") as get_identity,
    ):
        proof = await KratosInvitationSessionVerifier(
            frontend, AUTHORITY, identity_client=admin
        ).verify(COOKIE)

    assert proof == InvitationBrowserProofDTO(identity=IDENTITY, password_completed=None)
    get_identity.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["password", "oidc"])
async def test_confirmed_absence_is_not_inferred_from_session_method(method: str) -> None:
    frontend, admin = _frontend(), _admin()

    with (
        patch.object(frontend, "to_session", return_value=_session(method=method)),
        patch.object(admin, "get_identity", return_value=_identity(password=False)),
    ):
        proof = await KratosInvitationSessionVerifier(
            frontend, AUTHORITY, identity_client=admin
        ).verify(COOKIE, observe_password_completion=True)

    assert proof == InvitationBrowserProofDTO(identity=IDENTITY, password_completed=False)


@pytest.mark.asyncio
async def test_missing_admin_configuration_preserves_only_verified_identity() -> None:
    frontend = _frontend()

    with patch.object(frontend, "to_session", return_value=_session()):
        proof = await KratosInvitationSessionVerifier(frontend, AUTHORITY).verify(
            COOKIE, observe_password_completion=True
        )

    assert proof == InvitationBrowserProofDTO(identity=IDENTITY, password_completed=None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        ApiException(status=500, body="synthetic-sensitive-config"),
        ForbiddenException(status=403),
        HTTPError("synthetic-sensitive-config"),
        TimeoutError(),
    ],
)
async def test_unavailable_enrollment_does_not_deny_completed_replay_identity(
    error: Exception,
) -> None:
    frontend, admin = _frontend(), _admin()

    with (
        patch.object(frontend, "to_session", return_value=_session()),
        patch.object(admin, "get_identity", side_effect=error),
    ):
        proof = await KratosInvitationSessionVerifier(
            frontend, AUTHORITY, identity_client=admin
        ).verify(COOKIE, observe_password_completion=True)

    assert proof == InvitationBrowserProofDTO(identity=IDENTITY, password_completed=None)


@pytest.mark.asyncio
async def test_both_provider_calls_consume_one_original_budget() -> None:
    frontend, admin = _frontend(), _admin()

    with (
        patch(
            "inframeld_backend.access.infrastructure.verifiers."
            "kratos_invitation_session_verifier.monotonic",
            side_effect=[100.0, 101.0, 102.0, 103.0, 104.0],
        ),
        patch.object(frontend, "to_session", return_value=_session()) as to_session,
        patch.object(admin, "get_identity", return_value=_identity()) as get_identity,
    ):
        proof = await KratosInvitationSessionVerifier(
            frontend, AUTHORITY, identity_client=admin
        ).verify(COOKIE, observe_password_completion=True)

    assert proof == InvitationBrowserProofDTO(identity=IDENTITY, password_completed=True)
    assert to_session.call_args.kwargs["_request_timeout"] == 4.0
    assert get_identity.call_args.kwargs["_request_timeout"] == 2.0


@pytest.mark.asyncio
async def test_deadline_expiry_before_identity_is_unavailable() -> None:
    frontend = _frontend()

    with (
        patch(
            "inframeld_backend.access.infrastructure.verifiers."
            "kratos_invitation_session_verifier.monotonic",
            side_effect=[100.0, 101.0, 106.0],
        ),
        patch.object(frontend, "to_session", return_value=_session()),
        pytest.raises(DependencyUnavailableError),
    ):
        await KratosInvitationSessionVerifier(frontend, AUTHORITY).verify(COOKIE)


@pytest.mark.asyncio
async def test_deleted_identity_rejects_even_current_cookie() -> None:
    frontend, admin = _frontend(), _admin()

    with (
        patch.object(frontend, "to_session", return_value=_session()),
        patch.object(admin, "get_identity", side_effect=NotFoundException(status=404)),
    ):
        assert (
            await KratosInvitationSessionVerifier(
                frontend, AUTHORITY, identity_client=admin
            ).verify(COOKIE, observe_password_completion=True)
            is None
        )


@pytest.mark.asyncio
async def test_positive_identity_inactivation_is_not_optional_enrollment_failure() -> None:
    frontend, admin = _frontend(), _admin()
    identity = _identity()
    identity.state = "inactive"

    with (
        patch.object(frontend, "to_session", return_value=_session()),
        patch.object(admin, "get_identity", return_value=identity),
    ):
        assert (
            await KratosInvitationSessionVerifier(
                frontend, AUTHORITY, identity_client=admin
            ).verify(COOKIE, observe_password_completion=True)
            is None
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("identity_id", [None, "not-a-uuid", 42, UUID(int=99)])
async def test_malformed_or_mismatched_admin_identity_is_unavailable(identity_id: object) -> None:
    frontend, admin = _frontend(), _admin()
    identity = _identity().model_copy(update={"id": identity_id})

    with (
        patch.object(frontend, "to_session", return_value=_session()),
        patch.object(admin, "get_identity", return_value=identity),
        pytest.raises(DependencyUnavailableError),
    ):
        await KratosInvitationSessionVerifier(frontend, AUTHORITY, identity_client=admin).verify(
            COOKIE, observe_password_completion=True
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("state", [None, "unknown"])
async def test_malformed_admin_state_is_not_optional_failure(state: str | None) -> None:
    frontend, admin = _frontend(), _admin()
    identity = _identity().model_copy(update={"state": state})

    with (
        patch.object(frontend, "to_session", return_value=_session()),
        patch.object(admin, "get_identity", return_value=identity),
        pytest.raises(DependencyUnavailableError),
    ):
        await KratosInvitationSessionVerifier(frontend, AUTHORITY, identity_client=admin).verify(
            COOKIE, observe_password_completion=True
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("credential_type", [None, "oidc"])
async def test_contradictory_password_metadata_is_unavailable(
    credential_type: str | None,
) -> None:
    frontend, admin = _frontend(), _admin()
    identity = _identity()
    identity.credentials = {"password": IdentityCredentials(type=credential_type)}

    with (
        patch.object(frontend, "to_session", return_value=_session()),
        patch.object(admin, "get_identity", return_value=identity),
        pytest.raises(DependencyUnavailableError),
    ):
        await KratosInvitationSessionVerifier(frontend, AUTHORITY, identity_client=admin).verify(
            COOKIE, observe_password_completion=True
        )


@pytest.mark.asyncio
async def test_only_password_config_is_requested_and_no_payload_is_retained() -> None:
    frontend, admin = _frontend(), _admin()
    identity = _identity()
    identity.credentials = {
        "password": IdentityCredentials(
            type="password", config={"hashed_password": "never-retain-this"}
        )
    }

    with (
        patch.object(frontend, "to_session", return_value=_session()),
        patch.object(admin, "get_identity", return_value=identity) as get_identity,
    ):
        proof = await KratosInvitationSessionVerifier(
            frontend, AUTHORITY, identity_client=admin
        ).verify(COOKIE, observe_password_completion=True)

    assert proof == InvitationBrowserProofDTO(identity=IDENTITY, password_completed=True)
    assert "never-retain-this" not in repr(proof)
    assert get_identity.call_args.kwargs.keys() == {"id", "include_credential", "_request_timeout"}


@pytest.mark.asyncio
async def test_cancellation_propagates_without_becoming_password_absence() -> None:
    frontend, admin = _frontend(), _admin()

    with (
        patch.object(frontend, "to_session", return_value=_session()),
        patch.object(admin, "get_identity", side_effect=asyncio.CancelledError()),
        pytest.raises(asyncio.CancelledError),
    ):
        await KratosInvitationSessionVerifier(frontend, AUTHORITY, identity_client=admin).verify(
            COOKIE, observe_password_completion=True
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error", [UnauthorizedException(status=401), ForbiddenException(status=403)]
)
async def test_rejected_session_has_no_proof(error: ApiException) -> None:
    frontend = _frontend()

    with patch.object(frontend, "to_session", side_effect=error):
        assert await KratosInvitationSessionVerifier(frontend, AUTHORITY).verify(COOKIE) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_state", ["inactive-session", "expired-session", "disabled-identity"]
)
async def test_unusable_session_has_no_proof(invalid_state: str) -> None:
    frontend = _frontend()
    session = _session()
    if invalid_state == "inactive-session":
        session.active = False
    elif invalid_state == "expired-session":
        session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    else:
        assert session.identity is not None
        session.identity.state = "inactive"

    with patch.object(frontend, "to_session", return_value=session):
        assert await KratosInvitationSessionVerifier(frontend, AUTHORITY).verify(COOKIE) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_field", ["active", "expires_at", "identity"])
async def test_missing_session_evidence_is_unavailable(missing_field: str) -> None:
    frontend = _frontend()
    session = _session()
    setattr(session, missing_field, None)

    with (
        patch.object(frontend, "to_session", return_value=session),
        pytest.raises(DependencyUnavailableError),
    ):
        await KratosInvitationSessionVerifier(frontend, AUTHORITY).verify(COOKIE)


@pytest.mark.asyncio
@pytest.mark.parametrize("identity_id", [None, "not-a-uuid", 42])
async def test_malformed_session_identity_is_unavailable(identity_id: object) -> None:
    frontend = _frontend()
    session = _session()
    assert session.identity is not None
    session.identity = session.identity.model_copy(update={"id": identity_id})

    with (
        patch.object(frontend, "to_session", return_value=session),
        pytest.raises(DependencyUnavailableError),
    ):
        await KratosInvitationSessionVerifier(frontend, AUTHORITY).verify(COOKIE)


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [ApiException(status=500), HTTPError("connection failed")])
async def test_provider_failure_is_unavailable(error: Exception) -> None:
    frontend = _frontend()

    with (
        patch.object(frontend, "to_session", side_effect=error),
        pytest.raises(DependencyUnavailableError),
    ):
        await KratosInvitationSessionVerifier(frontend, AUTHORITY).verify(COOKIE)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "config", [None, {}, {"hashed_password": ""}, {"use_password_migration_hook": True}]
)
async def test_placeholder_or_migration_hook_is_not_a_stored_verifier(
    config: dict[str, object] | None,
) -> None:
    frontend, admin = _frontend(), _admin()
    identity = _identity()
    identity.credentials = {"password": IdentityCredentials(type="password", config=config)}
    with (
        patch.object(frontend, "to_session", return_value=_session()),
        patch.object(admin, "get_identity", return_value=identity),
    ):
        proof = await KratosInvitationSessionVerifier(
            frontend, AUTHORITY, identity_client=admin
        ).verify(COOKIE, observe_password_completion=True)
    assert proof == InvitationBrowserProofDTO(identity=IDENTITY, password_completed=False)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "config",
    [
        [],
        "synthetic-sensitive-config",
        {"hashed_password": None},
        {"hashed_password": 42},
        {"hashed_password": False},
    ],
)
async def test_malformed_password_evidence_is_safe_unavailable(config: object) -> None:
    frontend, admin = _frontend(), _admin()
    password = IdentityCredentials(type="password").model_copy(update={"config": config})
    identity = _identity().model_copy(update={"credentials": {"password": password}})
    with (
        patch.object(frontend, "to_session", return_value=_session()),
        patch.object(admin, "get_identity", return_value=identity),
        pytest.raises(DependencyUnavailableError) as caught,
    ):
        await KratosInvitationSessionVerifier(frontend, AUTHORITY, identity_client=admin).verify(
            COOKIE, observe_password_completion=True
        )
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert "synthetic-sensitive-config" not in "".join(traceback.format_exception(caught.value))


@pytest.mark.asyncio
@pytest.mark.parametrize("debug_source", ["frontend", "admin", "wire"])
async def test_wire_debugging_is_refused_before_any_provider_io(debug_source: str) -> None:
    frontend_config = Configuration(host="http://kratos.test")
    admin_config = Configuration(host="http://kratos-admin.test")
    frontend = FrontendApi(ApiClient(frontend_config))
    admin = IdentityApi(ApiClient(admin_config))
    with (
        patch.object(frontend_config, "_Configuration__debug", debug_source == "frontend"),
        patch.object(admin_config, "_Configuration__debug", debug_source == "admin"),
        patch.object(http.client.HTTPConnection, "debuglevel", int(debug_source == "wire")),
        patch.object(frontend, "to_session", return_value=_session()) as to_session,
        patch.object(admin, "get_identity", return_value=_identity()) as get_identity,
        pytest.raises(DependencyUnavailableError),
    ):
        await KratosInvitationSessionVerifier(frontend, AUTHORITY, identity_client=admin).verify(
            COOKIE, observe_password_completion=True
        )
    to_session.assert_not_called()
    get_identity.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["validation", "json", "unicode", "sdk"])
async def test_sensitive_sdk_validation_failure_has_no_raw_chain(failure: str) -> None:
    frontend, admin = _frontend(), _admin()

    def decode_invalid_identity(**_: object) -> Identity:
        if failure == "json":
            raise JSONDecodeError("Invalid JSON", "synthetic-sensitive-config", 0)
        if failure == "unicode":
            raise UnicodeDecodeError("utf-8", b"synthetic-sensitive-config", 0, 1, "invalid")
        if failure == "sdk":
            raise OpenApiException("synthetic-sensitive-config")
        return Identity.model_validate(
            {
                "credentials": {
                    "password": {"config": {"hashed_password": "synthetic-sensitive-config"}}
                }
            }
        )

    with (
        patch.object(frontend, "to_session", return_value=_session()),
        patch.object(admin, "get_identity", side_effect=decode_invalid_identity),
        pytest.raises(DependencyUnavailableError) as caught,
    ):
        await KratosInvitationSessionVerifier(frontend, AUTHORITY, identity_client=admin).verify(
            COOKIE, observe_password_completion=True
        )
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert "synthetic-sensitive-config" not in "".join(traceback.format_exception(caught.value))


@pytest.mark.asyncio
async def test_sensitive_unexpected_exception_is_safe_for_direct_and_asgi_callers() -> None:
    frontend, admin = _frontend(), _admin()
    verifier = KratosInvitationSessionVerifier(frontend, AUTHORITY, identity_client=admin)

    async def verify_request(request: Request) -> JSONResponse:
        await verifier.verify(COOKIE, observe_password_completion=True)
        return JSONResponse({"unexpected": "success"})

    application = Starlette(routes=[Route("/proof", verify_request)])
    with (
        patch.object(frontend, "to_session", return_value=_session()),
        patch.object(admin, "get_identity", side_effect=RuntimeError("synthetic-sensitive-config")),
        patch(
            "inframeld_backend.access.infrastructure.verifiers.kratos_invitation_session_verifier.logger"
        ) as logger,
    ):
        with pytest.raises(RuntimeError) as direct:
            await verifier.verify(COOKIE, observe_password_completion=True)
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=application), base_url="http://test"
        ) as client:
            with pytest.raises(RuntimeError) as asgi:
                await client.get("/proof")
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=application, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            response = await client.get("/proof")
    assert response.status_code == 500
    for error in [direct.value, asgi.value]:
        assert error.args == ("Invitation password observation failed unexpectedly.",)
        assert error.__cause__ is None and error.__context__ is None
        assert "synthetic-sensitive-config" not in "".join(traceback.format_exception(error))
    assert logger.error.call_count == 3
    for call in logger.error.call_args_list:
        serialized = json.dumps(call.kwargs)
        assert "synthetic-sensitive-config" not in serialized
        assert call.kwargs["diagnostic"]["type"] == "RuntimeError"
        assert call.kwargs["diagnostic"]["frames"]
        assert "exc_info" not in call.kwargs


@pytest.mark.asyncio
async def test_missing_password_slot_is_confirmed_absence() -> None:
    frontend, admin = _frontend(), _admin()
    identity = _identity().model_copy(update={"credentials": {}})
    with (
        patch.object(frontend, "to_session", return_value=_session()),
        patch.object(admin, "get_identity", return_value=identity),
    ):
        proof = await KratosInvitationSessionVerifier(
            frontend, AUTHORITY, identity_client=admin
        ).verify(COOKIE, observe_password_completion=True)
    assert proof == InvitationBrowserProofDTO(identity=IDENTITY, password_completed=False)
