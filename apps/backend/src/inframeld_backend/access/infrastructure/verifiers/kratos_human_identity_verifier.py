import asyncio
import math
from enum import StrEnum
from json import JSONDecodeError
from time import monotonic
from typing import override
from uuid import UUID

from ory_kratos_client.api.identity_api import IdentityApi
from ory_kratos_client.exceptions import NotFoundException, OpenApiException
from ory_kratos_client.models.identity import Identity
from pydantic import ValidationError
from urllib3.exceptions import HTTPError

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.human_identity_verifier import (
    HumanIdentityVerifier,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)


class KratosIdentityState(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class KratosHumanIdentityVerifier(HumanIdentityVerifier):
    """Check whether a given identity is currently valid in Kratos.

    Bootstrap owns the private SDK client, its connection pool, TLS settings,
    disabled retries and disabled debug logging. Each verification performs a
    fresh lookup by identity ID without requesting provider credentials.
    """

    def __init__(self, client: IdentityApi, authority: IdentityAuthority) -> None:
        self._client = client
        self._authority = authority

    # region Internal Helpers
    def _get_identity(self, subject: UUID, deadline: float) -> Identity:
        remaining = deadline - monotonic()

        if remaining <= 0:
            raise TimeoutError

        return self._client.get_identity(id=str(subject), _request_timeout=remaining)

    def _read_identity(
        self,
        response: object,
        subject: UUID,
        identity: VerifiedHumanIdentityDTO,
    ) -> VerifiedHumanIdentityDTO | None:
        if not isinstance(response, Identity):
            raise DependencyUnavailableError()

        try:
            returned_subject = UUID(response.id)
            state = KratosIdentityState(response.state)
        except (TypeError, ValueError):
            raise DependencyUnavailableError() from None

        if returned_subject != subject:
            raise DependencyUnavailableError()

        if state is KratosIdentityState.INACTIVE:
            return None

        return identity

    # endregion

    @override
    async def verify(
        self,
        identity: VerifiedHumanIdentityDTO,
        *,
        timeout_seconds: float,
    ) -> VerifiedHumanIdentityDTO | None:
        if (
            isinstance(timeout_seconds, bool)
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise ValueError("The provider timeout must be finite and positive.")

        if identity.authority != self._authority:
            return None

        try:
            subject = UUID(identity.subject.value)
        except ValueError:
            return None

        deadline = monotonic() + timeout_seconds

        try:
            async with asyncio.timeout(timeout_seconds):
                try:
                    response = await asyncio.to_thread(
                        self._get_identity,
                        subject,
                        deadline,
                    )
                except NotFoundException:
                    result = None
                else:
                    result = self._read_identity(response, subject, identity)

                if monotonic() >= deadline:
                    raise TimeoutError

                return result
        except (
            OpenApiException,
            HTTPError,
            ValidationError,
            JSONDecodeError,
            UnicodeDecodeError,
            TimeoutError,
        ):
            # SDK failures can contain sensitive provider response bodies.
            raise DependencyUnavailableError() from None
