import asyncio
import math
from dataclasses import replace
from datetime import UTC, datetime
from enum import StrEnum
from http.client import HTTPConnection
from json import JSONDecodeError
from time import monotonic
from typing import cast, final, override

import structlog
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
from pydantic import ValidationError
from urllib3.exceptions import HTTPError

from inframeld_backend.access.application.dtos.invitation_browser_proof_dto import (
    InvitationBrowserProofDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.invitation_session_verifier import (
    InvitationSessionVerifier,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.domain.validation.value_validation import ValueValidation
from inframeld_backend.shared.infrastructure.diagnostics.safe_exception_diagnostic import (
    build_safe_exception_diagnostic,
)

logger = structlog.get_logger(__name__)


class _KratosIdentityState(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class _KratosCredentialType(StrEnum):
    PASSWORD = "password"


@final
class KratosInvitationSessionVerifier(InvitationSessionVerifier):
    """Observe identity and reduce private password evidence before it leaves its thread.

    The lifespan owns both injected SDK pools. All provider work precedes SQL.
    Preview avoids the private credential read. Its absence or unavailability is
    not a fresh prerequisite for an eligible completed-recipient replay.
    """

    def __init__(
        self,
        client: FrontendApi,
        authority: IdentityAuthority,
        timeout_seconds: float = 5.0,
        *,
        identity_client: IdentityApi | None = None,
    ) -> None:
        if (
            isinstance(timeout_seconds, bool)
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise ValueError("The provider timeout must be finite and positive.")

        self._client = client
        self._authority = authority
        self._timeout_seconds = timeout_seconds
        self._identity_client = identity_client

    @staticmethod
    def _remaining(deadline: float) -> float:
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise TimeoutError
        return remaining

    def _read_identity(self, identity: object) -> VerifiedHumanIdentityDTO | None:
        if not isinstance(identity, Identity):
            raise DependencyUnavailableError()

        try:
            state = _KratosIdentityState(identity.state)
            ValueValidation.require_uuid(identity.id)
            subject = IdentitySubject(str(identity.id))
        except (TypeError, ValueError):
            raise DependencyUnavailableError() from None

        if state is _KratosIdentityState.INACTIVE:
            return None

        return VerifiedHumanIdentityDTO(authority=self._authority, subject=subject)

    def _read_session(self, session: object) -> InvitationBrowserProofDTO | None:
        if not isinstance(session, Session):
            raise DependencyUnavailableError()

        if session.active is None:
            raise DependencyUnavailableError()
        if not session.active:
            return None

        if (
            session.expires_at is None
            or session.expires_at.utcoffset() is None
            or session.identity is None
        ):
            raise DependencyUnavailableError()
        if session.expires_at <= datetime.now(UTC):
            return None

        identity = self._read_identity(session.identity)
        if identity is None:
            return None

        return InvitationBrowserProofDTO(identity=identity, password_completed=None)

    @staticmethod
    def _sdk_debug_enabled(client: FrontendApi | IdentityApi) -> bool:
        # The pinned SDK leaves these constructor-populated attributes untyped.
        api_client: object = getattr(client, "api_client", None)
        if not isinstance(api_client, ApiClient):
            raise DependencyUnavailableError()
        configuration: object = getattr(api_client, "configuration", None)
        if not isinstance(configuration, Configuration):
            raise DependencyUnavailableError()
        return configuration.debug

    def _require_private_transport(self, *, observe_password_completion: bool) -> None:
        if (
            HTTPConnection.debuglevel
            or self._sdk_debug_enabled(self._client)
            or (
                observe_password_completion
                and self._identity_client is not None
                and self._sdk_debug_enabled(self._identity_client)
            )
        ):
            raise DependencyUnavailableError()

    def _read_password_completion(
        self, proof: InvitationBrowserProofDTO, deadline: float
    ) -> InvitationBrowserProofDTO | None:
        """Keep the credential-bearing response local to the confidential sync boundary."""
        if self._identity_client is None:
            return proof

        metadata = self._identity_client.get_identity(
            id=proof.identity.subject.value,
            include_credential=["password"],
            _request_timeout=self._remaining(deadline),
        )
        self._remaining(deadline)
        current_identity = self._read_identity(metadata)
        if str(metadata.id) != proof.identity.subject.value:
            raise DependencyUnavailableError()
        if current_identity is None:
            return None

        password = cast(object, (metadata.credentials or {}).get(_KratosCredentialType.PASSWORD))
        if password is None:
            return replace(proof, password_completed=False)
        if (
            not isinstance(password, IdentityCredentials)
            or password.type != _KratosCredentialType.PASSWORD
        ):
            raise DependencyUnavailableError()

        # SDK configuration dictionaries stay at this provider serialization boundary.
        config = cast(object, password.config)
        if config is None:
            return replace(proof, password_completed=False)
        if not isinstance(config, dict):
            raise DependencyUnavailableError()
        if "hashed_password" not in config:
            return replace(proof, password_completed=False)

        stored_verifier = cast(dict[str, object], config)["hashed_password"]
        if not isinstance(stored_verifier, str):
            raise DependencyUnavailableError()
        return replace(proof, password_completed=bool(stored_verifier))

    def _observe_password_completion(
        self, proof: InvitationBrowserProofDTO, deadline: float
    ) -> InvitationBrowserProofDTO | None:
        """Contain SDK payloads and exception chains before returning to async callers.

        Raise safe replacements outside the catch so even direct callers and ASGI
        rethrows cannot render a raw credential-bearing exception context.
        """
        diagnostic: dict[str, object] | None = None
        try:
            return self._read_password_completion(proof, deadline)
        except NotFoundException:
            return None
        except (ApiException, HTTPError, TimeoutError):
            return proof
        except (
            OpenApiException,
            ValidationError,
            JSONDecodeError,
            UnicodeDecodeError,
            DependencyUnavailableError,
        ):
            pass
        except Exception as error:
            diagnostic = build_safe_exception_diagnostic((type(error), error, error.__traceback__))

        if diagnostic is not None:
            logger.error("invitation_password_observation_failed", diagnostic=diagnostic)
            raise RuntimeError("Invitation password observation failed unexpectedly.")
        raise DependencyUnavailableError()

    @override
    async def verify(
        self,
        credential: BrowserSessionCredential,
        *,
        observe_password_completion: bool = False,
    ) -> InvitationBrowserProofDTO | None:
        self._require_private_transport(observe_password_completion=observe_password_completion)
        deadline = monotonic() + self._timeout_seconds
        proof: InvitationBrowserProofDTO | None = None
        try:
            async with asyncio.timeout(self._timeout_seconds):
                try:
                    session = await asyncio.to_thread(
                        self._client.to_session,
                        cookie=f"ory_kratos_session={credential.value}",
                        _request_timeout=self._remaining(deadline),
                    )
                except (UnauthorizedException, ForbiddenException):
                    return None
                except (
                    OpenApiException,
                    HTTPError,
                    ValidationError,
                    JSONDecodeError,
                    UnicodeDecodeError,
                ):
                    raise DependencyUnavailableError() from None

                self._remaining(deadline)
                proof = self._read_session(session)
                if (
                    proof is None
                    or not observe_password_completion
                    or self._identity_client is None
                ):
                    return proof

                return await asyncio.to_thread(self._observe_password_completion, proof, deadline)
        except TimeoutError:
            if proof is not None:
                return proof
            raise DependencyUnavailableError() from None
