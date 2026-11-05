import asyncio
import math
from hmac import compare_digest
from typing import override
from uuid import UUID, uuid4

from inframeld_backend.access.application.commands.bootstrap_first_administrator_command import (
    BootstrapFirstAdministratorCommand,
)
from inframeld_backend.access.application.dtos.first_administrator_bootstrap_receipt_dto import (
    FirstAdministratorBootstrapReceiptDTO,
)
from inframeld_backend.access.application.dtos.first_administrator_bootstrap_result_dto import (
    FirstAdministratorBootstrapResultDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.enums.first_administrator_bootstrap_error_code import (
    FirstAdministratorBootstrapErrorCode as Code,
)
from inframeld_backend.access.application.errors.first_administrator_bootstrap_error import (
    FirstAdministratorBootstrapError,
)
from inframeld_backend.access.application.protocols.first_administrator_bootstrap_facts_reader import (
    FirstAdministratorBootstrapFactsReader,
)
from inframeld_backend.access.application.protocols.first_administrator_bootstrap_writer import (
    FirstAdministratorBootstrapWriter,
)
from inframeld_backend.access.application.protocols.first_administrator_bootstrapper import (
    FirstAdministratorBootstrapper,
)
from inframeld_backend.access.application.protocols.human_access_token_verifier import (
    HumanAccessTokenVerifier,
)
from inframeld_backend.access.application.protocols.human_identity_verifier import (
    HumanIdentityVerifier,
)
from inframeld_backend.access.application.services.first_administrator_bootstrap_fingerprint_service import (
    FirstAdministratorBootstrapFingerprintService,
)
from inframeld_backend.access.domain.policies.first_administrator_bootstrap_policy import (
    FirstAdministratorBootstrapPolicy,
)
from inframeld_backend.access.domain.policies.human_credential_policy import HumanCredentialPolicy
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)


class FirstAdministratorBootstrapService(FirstAdministratorBootstrapper):
    def __init__(
        self,
        *,
        token_verifier: HumanAccessTokenVerifier,
        identity_verifier: HumanIdentityVerifier,
        transaction_manager: TransactionManager,
        bootstrap_facts_reader: FirstAdministratorBootstrapFactsReader,
        bootstrap_writer: FirstAdministratorBootstrapWriter,
        bootstrap_fingerprint_service: FirstAdministratorBootstrapFingerprintService,
        provider_timeout_seconds: float = 5.0,
        total_timeout_seconds: float = 10.0,
    ) -> None:
        for seconds in (provider_timeout_seconds, total_timeout_seconds):
            if isinstance(seconds, bool) or not math.isfinite(seconds) or seconds <= 0:
                raise ValueError("Proof verification requires finite positive timeouts.")
        self._token_verifier = token_verifier
        self._identity_verifier = identity_verifier
        self._transaction_manager = transaction_manager
        self._bootstrap_facts_reader = bootstrap_facts_reader
        self._bootstrap_writer = bootstrap_writer
        self._bootstrap_fingerprint_service = bootstrap_fingerprint_service
        self._provider_timeout_seconds = provider_timeout_seconds
        self._total_timeout_seconds = total_timeout_seconds

    @override
    async def bootstrap(
        self, command: BootstrapFirstAdministratorCommand
    ) -> FirstAdministratorBootstrapResultDTO:
        binding = await self._verify(command)
        fingerprint = self._bootstrap_fingerprint_service.for_bootstrap(command, binding.identity)
        try:
            async with asyncio.timeout(5):
                async with self._transaction_manager.begin():
                    return await self._claim(command, binding, fingerprint)
        except TimeoutError:
            raise FirstAdministratorBootstrapError(Code.DEPENDENCY_UNAVAILABLE) from None

    def _provider_budget(self, deadline: float) -> float:
        """Limit provider verification to the time left in the original bootstrap request."""
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise TimeoutError()
        return min(self._provider_timeout_seconds, remaining)

    async def _verify(
        self, command: BootstrapFirstAdministratorCommand
    ) -> HumanOAuthCredentialBindingDTO:
        """Verify the human with both providers before entering the database claim."""
        deadline = asyncio.get_running_loop().time() + self._total_timeout_seconds
        try:
            async with asyncio.timeout_at(deadline):
                binding = await self._token_verifier.verify(
                    command.identity_proof, timeout_seconds=self._provider_budget(deadline)
                )
                if binding is None:
                    raise FirstAdministratorBootstrapError(Code.INVALID_IDENTITY_PROOF)
                identity = await self._identity_verifier.verify(
                    binding.identity, timeout_seconds=self._provider_budget(deadline)
                )
                if identity is None or identity != binding.identity:
                    raise FirstAdministratorBootstrapError(Code.INVALID_IDENTITY_PROOF)
                try:
                    identity_id = UUID(identity.subject.value)
                except ValueError:
                    raise FirstAdministratorBootstrapError(Code.INVALID_IDENTITY_PROOF) from None
                if identity_id != command.expected_identity_id:
                    raise FirstAdministratorBootstrapError(Code.INVALID_IDENTITY_PROOF)
                if binding.installation_id != command.expected_installation_id:
                    raise FirstAdministratorBootstrapError(Code.INSTALLATION_MISMATCH)
                return binding
        except (TimeoutError, DependencyUnavailableError):
            raise FirstAdministratorBootstrapError(Code.DEPENDENCY_UNAVAILABLE) from None

    async def _claim(
        self,
        command: BootstrapFirstAdministratorCommand,
        binding: HumanOAuthCredentialBindingDTO,
        fingerprint: RequestFingerprint,
    ) -> FirstAdministratorBootstrapResultDTO:
        """Establish the first administrator from current locked installation and identity facts."""
        facts = await self._bootstrap_facts_reader.read(
            installation_id=command.expected_installation_id, identity=binding.identity
        )
        state = facts.credential_state
        if (
            facts.installation_id != command.expected_installation_id
            or facts.identity != binding.identity
            or state.installation_id != facts.installation_id
            or state.identity != facts.identity
        ):
            raise RuntimeError("Coordinated bootstrap facts changed their verified scope.")
        if not HumanCredentialPolicy.is_current(
            installation_id=binding.installation_id,
            authority=binding.identity.authority,
            subject=binding.identity.subject,
            version=binding.version,
            current_installation_id=state.installation_id,
            current_authority=state.identity.authority,
            current_subject=state.identity.subject,
            current_version=state.version,
        ):
            raise FirstAdministratorBootstrapError(Code.INVALID_IDENTITY_PROOF)
        if not FirstAdministratorBootstrapPolicy.may_admit(
            principal=facts.principal, has_pending_recovery=state.has_pending_recovery
        ):
            raise FirstAdministratorBootstrapError(Code.IDENTITY_INELIGIBLE)

        recorded = await self._bootstrap_facts_reader.receipt(
            installation_id=facts.installation_id, operation_id=command.operation_id
        )
        if recorded is not None:
            if (
                recorded.identity != binding.identity
                or recorded.expected_identity_id != command.expected_identity_id
                or recorded.result.operation_id != command.operation_id
                or recorded.result.installation_id != facts.installation_id
                or not compare_digest(recorded.fingerprint.value, fingerprint.value)
            ):
                raise FirstAdministratorBootstrapError(Code.KEY_REUSED)
            if (
                facts.principal is None
                or facts.principal.id != recorded.result.recipient_id
                or facts.principal.organization_id != recorded.result.organization_id
            ):
                raise FirstAdministratorBootstrapError(Code.IDENTITY_INELIGIBLE)
            if (
                not facts.has_bootstrap_claim
                or recorded.before_revision != 0
                or recorded.result.access_revision != 1
            ):
                raise RuntimeError("The bootstrap receipt has no coherent original claim.")
            return recorded.result

        if facts.has_bootstrap_claim:
            raise FirstAdministratorBootstrapError(Code.ALREADY_BOOTSTRAPPED)
        if facts.has_business_state:
            raise FirstAdministratorBootstrapError(Code.DEPENDENCY_UNAVAILABLE)
        if command.expected_access_revision != 0:
            raise FirstAdministratorBootstrapError(Code.STALE_REVISION)

        result = FirstAdministratorBootstrapResultDTO(
            command.operation_id,
            facts.installation_id,
            OrganizationId(uuid4()),
            PrincipalId(uuid4()),
            1,
        )
        receipt = FirstAdministratorBootstrapReceiptDTO(
            fingerprint,
            binding.identity,
            command.expected_identity_id,
            command.operator_label,
            command.reason,
            0,
            facts.observed_at,
            result,
        )
        if not await self._bootstrap_writer.bootstrap(facts=facts, receipt=receipt):
            raise FirstAdministratorBootstrapError(Code.KEY_REUSED)
        return result
