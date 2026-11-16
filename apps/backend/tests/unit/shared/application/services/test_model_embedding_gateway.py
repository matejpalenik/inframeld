import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from ipaddress import IPv4Address
from json import dumps
from logging import CRITICAL
from ssl import create_default_context
from sys import modules
from time import monotonic
from types import ModuleType
from typing import cast, override
from unittest.mock import create_autospec
from uuid import uuid4

import pytest

from inframeld_backend.access.application.dtos.admitted_work_authority_dto import (
    AdmittedWorkAuthorityDTO,
)
from inframeld_backend.access.application.dtos.encrypted_provider_credential_dto import (
    EncryptedProviderCredentialDTO,
)
from inframeld_backend.access.application.dtos.model_connection_access_dto import (
    ModelConnectionAccessDTO,
)
from inframeld_backend.access.application.dtos.model_dispatch_credential_dto import (
    ModelDispatchCredentialDTO,
)
from inframeld_backend.access.application.dtos.provider_credential_binding_dto import (
    ProviderCredentialBindingDTO,
)
from inframeld_backend.access.application.services.model_dispatch_credential_service import (
    ModelDispatchCredentialService,
)
from inframeld_backend.access.domain.enums.model_connection_authentication import (
    ModelConnectionAuthentication,
)
from inframeld_backend.access.domain.enums.model_connection_provider import ModelConnectionProvider
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.admitted_embedding_call_dto import (
    AdmittedEmbeddingCallDTO,
)
from inframeld_backend.shared.application.dtos.captured_spending_basis_dto import (
    CapturedSpendingBasisDTO,
)
from inframeld_backend.shared.application.dtos.effective_model_settings_dto import (
    EffectiveModelSettingsDTO,
)
from inframeld_backend.shared.application.dtos.embedding_dispatch_result_dto import (
    EmbeddingDispatchResultDTO,
)
from inframeld_backend.shared.application.dtos.embedding_model_settings_dto import (
    EmbeddingModelSettingsDTO,
)
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.dtos.model_dispatch_issuance_dto import (
    ModelDispatchIssuanceDTO,
)
from inframeld_backend.shared.application.dtos.model_selection_dto import ModelSelectionDTO
from inframeld_backend.shared.application.dtos.model_token_bound_dto import ModelTokenBoundDTO
from inframeld_backend.shared.application.dtos.product_job_binding_dto import ProductJobBindingDTO
from inframeld_backend.shared.application.dtos.reviewed_model_settings_dto import (
    ReviewedModelSettingsDTO,
)
from inframeld_backend.shared.application.dtos.spending_accounting_result_dto import (
    SpendingAccountingResultDTO,
)
from inframeld_backend.shared.application.dtos.spending_call_context_dto import (
    SpendingCallContextDTO,
)
from inframeld_backend.shared.application.dtos.spending_call_record_dto import SpendingCallRecordDTO
from inframeld_backend.shared.application.dtos.spending_observation_dto import (
    SpendingObservationDTO,
)
from inframeld_backend.shared.application.dtos.spending_rate_dto import SpendingRateDTO
from inframeld_backend.shared.application.dtos.spending_usage_dto import SpendingUsageDTO
from inframeld_backend.shared.application.enums.embedding_distance import EmbeddingDistance
from inframeld_backend.shared.application.enums.embedding_normalization import (
    EmbeddingNormalization,
)
from inframeld_backend.shared.application.enums.model_role import ModelRole
from inframeld_backend.shared.application.enums.model_token_bound_kind import ModelTokenBoundKind
from inframeld_backend.shared.application.enums.spending_call_state import SpendingCallState
from inframeld_backend.shared.application.enums.spending_observation_kind import (
    SpendingObservationKind,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.errors.job_errors import JobFenceLostError
from inframeld_backend.shared.application.protocols.model_dispatch_issuance_repository import (
    ModelDispatchIssuanceRepository,
)
from inframeld_backend.shared.application.protocols.model_embedding_adapter import (
    ModelEmbeddingAdapter,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.application.services.model_embedding_gateway import (
    ModelDispatchPhase,
    ModelEmbeddingGateway,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.services.spending_accounting_service import (
    SpendingAccountingService,
)
from inframeld_backend.shared.application.value_objects.job_fence import JobFence
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.application.value_objects.model_call_id import ModelCallId
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.application.value_objects.spending_period import SpendingPeriod
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.domain.value_objects.usd_amount import UsdAmount

_NOW = datetime.now(UTC)
_PROJECT = ProjectId(uuid4())
_CONNECTION = ModelConnectionId(uuid4())
_AUTHORITY = AdmittedWorkAuthorityDTO(
    principal_id=PrincipalId(uuid4()),
    principal_kind=PrincipalKind.APPLICATION,
    installation_id=InstallationId(uuid4()),
    organization_id=OrganizationId(uuid4()),
    project_id=_PROJECT,
    action_id=ActionId("inspect-budget"),
    human_binding=None,
)
_BINDING = ProductJobBindingDTO(OperationId("original-embedding"), RequestId(uuid4()), _AUTHORITY)
_CREDENTIAL = ModelDispatchCredentialDTO(
    ModelConnectionAccessDTO(
        ModelConnectionProvider.OPENAI_COMPATIBLE,
        "https://fixture.example.test/v1",
        None,
        ModelConnectionAuthentication.API_KEY,
    ),
    3,
    ProviderCredentialBindingDTO(_AUTHORITY.organization_id, _PROJECT, _CONNECTION, uuid4(), 2),
    EncryptedProviderCredentialDTO(1, "xchacha20-poly1305", "a" * 64, b"r" * 54),
)
_CALL = AdmittedEmbeddingCallDTO(
    ReviewedModelSettingsDTO(
        ModelSelectionDTO(_PROJECT, _CONNECTION, "text-embedding-3-small", ModelRole.EMBEDDING),
        EffectiveModelSettingsDTO(
            8,
            ModelTokenBoundDTO(ModelTokenBoundKind.EXACT, "fixture-tokenizer", "test-v1"),
            EmbeddingModelSettingsDTO(
                3,
                EmbeddingNormalization.NONE,
                EmbeddingDistance.COSINE,
                "",
                "",
                "openai-compatible",
                role=ModelRole.EMBEDDING,
            ),
        ),
        "reviewed-embedding",
    ),
    3,
    (31, 32),
    CapturedSpendingBasisDTO(
        "fixture-rate",
        "trusted fixture",
        "test-v1",
        _NOW,
        (SpendingRateDTO("input", "token", Decimal("0.10")),),
        (SpendingUsageDTO("input", "token", Decimal(2)),),
    ),
    UsdAmount(Decimal("1")),
)
_FINGERPRINTS = RequestFingerprintService(RequestFingerprintKey(b"F" * 32))


class MockTransaction(TransactionManager):
    def __init__(self) -> None:
        self.active = False
        self.session_open = False
        self.commits = 0
        self.rollbacks = 0
        self.lose_acknowledgment = False

    @override
    @asynccontextmanager
    async def begin(self) -> AsyncGenerator[None]:
        assert not self.active
        self.active = True
        try:
            yield
            self.commits += 1
            if self.lose_acknowledgment:
                raise ConnectionError("Issued transaction acknowledgment lost.")
        except JobFenceLostError:
            self.rollbacks += 1
            raise
        finally:
            self.active = False


class MockIssuances(ModelDispatchIssuanceRepository):
    def __init__(self, transaction: MockTransaction) -> None:
        self.transaction = transaction
        self.issued: ModelDispatchIssuanceDTO | None = None
        self.checkpoint: bytes | None = None
        self.remaining = timedelta(seconds=30)
        self.lost_at_confirmation: JobFenceLostError | None = None

    @override
    async def add(
        self, attempt: JobAttemptContextDTO, issuance: ModelDispatchIssuanceDTO
    ) -> timedelta:
        assert self.transaction.active and self.issued is None
        assert issuance.fence == attempt.fence
        self.issued = issuance
        return self.remaining

    @override
    async def get(self, call_id: ModelCallId) -> ModelDispatchIssuanceDTO | None:
        current = self.issued
        return current if current is not None and current.call_id == call_id else None

    @override
    async def confirm(
        self, attempt: JobAttemptContextDTO, call_id: ModelCallId, checkpoint: bytes
    ) -> bool:
        assert self.transaction.active and self.issued is not None
        assert self.issued.call_id == call_id and self.issued.fence == attempt.fence
        if self.lost_at_confirmation is not None:
            raise self.lost_at_confirmation
        self.checkpoint = checkpoint
        return True


class MockAdapter(ModelEmbeddingAdapter):
    def __init__(self, transaction: MockTransaction) -> None:
        self.transaction = transaction
        self.invocations = 0

    @override
    def prepare(self) -> None:
        assert not self.transaction.session_open

    @override
    def require_supported(
        self, call: AdmittedEmbeddingCallDTO, credential: ModelDispatchCredentialDTO
    ) -> str:
        assert self.transaction.active and call == _CALL and credential == _CREDENTIAL
        return "fixed-adapter"

    @override
    async def embed(
        self,
        call: AdmittedEmbeddingCallDTO,
        credential: ModelDispatchCredentialDTO,
        *,
        dispatch_deadline: float,
    ) -> EmbeddingDispatchResultDTO:
        assert not self.transaction.active and not self.transaction.session_open
        assert self.transaction.commits == 1
        assert monotonic() < dispatch_deadline
        assert call.tokens == (31, 32) and credential == _CREDENTIAL
        self.invocations += 1
        return EmbeddingDispatchResultDTO(SpendingObservationKind.USAGE, (0.1, 0.2, 0.3), 2)


class GatewayScenario:
    def __init__(self) -> None:
        self.transactions = MockTransaction()
        self.issuances = MockIssuances(self.transactions)
        self.adapter = MockAdapter(self.transactions)
        self.settled = False
        self.observed: SpendingObservationDTO | None = None
        self.late: SpendingObservationDTO | None = None
        credentials = create_autospec(ModelDispatchCredentialService, instance=True)
        credentials.read.return_value = _CREDENTIAL
        spending = create_autospec(SpendingAccountingService, instance=True)
        spending.prepare_new_dispatch_in_transaction.side_effect = self.prepare
        spending.record_observation_in_transaction.side_effect = self.observe
        spending.retain_late_observation_in_transaction.side_effect = self.retain_late

        @asynccontextmanager
        async def phase() -> AsyncGenerator[ModelDispatchPhase]:
            self.transactions.session_open = True
            try:
                yield self.transactions, credentials, spending, self.issuances
            finally:
                self.transactions.session_open = False

        self.gateway = ModelEmbeddingGateway(phase, self.adapter, _FINGERPRINTS)
        self.attempt = JobAttemptContextDTO(
            JobId(uuid4()),
            _BINDING,
            self.gateway.admission_payload(_CALL),
            1,
            JobFence(uuid4()),
            _NOW + timedelta(minutes=5),
            b"",
        )

    async def prepare(
        self,
        *,
        call: SpendingCallContextDTO,
        basis: CapturedSpendingBasisDTO,
        operation_limit: UsdAmount | None,
    ) -> SpendingAccountingResultDTO:
        assert self.transactions.active and self.transactions.session_open
        assert basis == _CALL.basis and operation_limit == _CALL.operation_limit
        if self.issuances.issued is not None:
            raise ConflictError("No repeat issuance.")
        return SpendingAccountingResultDTO(
            self.record(call, SpendingCallState.ACCOUNTING_APPROVED, 1)
        )

    async def observe(
        self,
        *,
        call: SpendingCallContextDTO,
        observation: SpendingObservationDTO,
        expected_call_revision: int,
    ) -> SpendingAccountingResultDTO:
        assert self.transactions.active and expected_call_revision == 1
        assert (
            observation.call_id == call.call_id and observation.usage == _CALL.basis.maximum_usage
        )
        self.settled = True
        self.observed = observation
        return SpendingAccountingResultDTO(self.record(call, SpendingCallState.SETTLED, 2))

    async def retain_late(
        self,
        *,
        call: SpendingCallContextDTO,
        observation: SpendingObservationDTO,
        expected_call_revision: int,
    ) -> None:
        assert self.transactions.active and self.transactions.rollbacks == 1
        assert self.transactions.commits == 1 and expected_call_revision == 1
        assert self.issuances.issued is not None and call.call_id == self.issuances.issued.call_id
        self.late = observation

    @staticmethod
    def record(
        call: SpendingCallContextDTO, state: SpendingCallState, revision: int
    ) -> SpendingCallRecordDTO:
        return SpendingCallRecordDTO(
            call.call_id,
            call.operation_id,
            call.authority,
            call.attempt.job_id,
            call.meaning_fingerprint,
            SpendingPeriod.from_instant(_NOW),
            _CALL.operation_limit,
            _CALL.basis,
            UsdAmount(Decimal("0.2")),
            UsdAmount(Decimal("0.2")),
            None,
            state,
            revision,
            0,
        )


@pytest.mark.asyncio
async def test_embedding_dispatch_follows_one_acknowledged_issuance_and_confirms_settlement() -> (
    None
):
    scenario = GatewayScenario()

    result = await scenario.gateway.embed(scenario.attempt, _CALL)

    assert result.vector == (0.1, 0.2, 0.3)
    assert scenario.adapter.invocations == 1 and scenario.settled
    assert scenario.transactions.commits == 2 and scenario.issuances.checkpoint is not None
    with pytest.raises(ConflictError):
        await scenario.gateway.embed(scenario.attempt, _CALL)
    assert scenario.adapter.invocations == 1


@pytest.mark.asyncio
async def test_lost_issuance_acknowledgment_never_enters_the_adapter() -> None:
    scenario = GatewayScenario()
    scenario.transactions.lose_acknowledgment = True

    with pytest.raises(ConnectionError):
        await scenario.gateway.embed(scenario.attempt, _CALL)

    assert scenario.issuances.issued is not None and scenario.adapter.invocations == 0


@pytest.mark.asyncio
async def test_replacing_tokens_in_admitted_work_cannot_create_a_new_call() -> None:
    scenario = GatewayScenario()

    with pytest.raises(ConflictError):
        await scenario.gateway.embed(scenario.attempt, replace(_CALL, tokens=(31, 33)))

    assert scenario.issuances.issued is None and scenario.adapter.invocations == 0


@pytest.mark.asyncio
async def test_acknowledgment_after_lease_deadline_cannot_enter_the_adapter() -> None:
    scenario = GatewayScenario()
    scenario.issuances.remaining = timedelta(0)

    with pytest.raises(JobFenceLostError):
        await scenario.gateway.embed(scenario.attempt, _CALL)

    assert scenario.issuances.issued is not None and scenario.adapter.invocations == 0


@pytest.mark.asyncio
async def test_fence_lost_at_confirmation_retains_the_original_observation_after_rollback() -> None:
    scenario = GatewayScenario()
    expected = JobFenceLostError("Original fence expired at confirmation.")
    scenario.issuances.lost_at_confirmation = expected

    with pytest.raises(JobFenceLostError) as raised:
        await scenario.gateway.embed(scenario.attempt, _CALL)

    assert raised.value is expected
    assert scenario.observed is not None and scenario.late is scenario.observed
    assert scenario.transactions.commits == 2 and scenario.transactions.rollbacks == 1
    assert scenario.issuances.checkpoint is None and scenario.adapter.invocations == 1


def test_sdk_preflight_rejects_an_effective_poison_callback(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from inframeld_backend.access.infrastructure.resources.pynacl_provider_credential_cipher import (
        PyNaClProviderCredentialCipher,
    )
    from inframeld_backend.shared.infrastructure.resources.litellm_embedding_adapter import (
        LiteLLMEmbeddingAdapter,
    )

    def forbidden_callback(*_arguments: object) -> None:
        pytest.fail("An unapproved callback was executed.")

    sdk = ModuleType("litellm")
    sdk.__dict__.update(
        DEFAULT_MAX_RETRIES=0,
        global_disable_no_log_param=False,
        set_verbose=False,
        callbacks=[],
        input_callback=[forbidden_callback],
        success_callback=[],
        failure_callback=[],
        service_callback=[],
        audit_log_callbacks=[],
        batch_line_item_callbacks=(),
        _async_input_callback=[],
        _async_success_callback=[],
        _async_failure_callback=[],
        pre_call_rules=[],
        post_call_rules=[],
    )
    monkeypatch.setitem(modules, "litellm", sdk)
    for name, value in {
        "LITELLM_MODE": "PRODUCTION",
        "LITELLM_LOCAL_MODEL_COST_MAP": "True",
        "LITELLM_TELEMETRY_DISABLED": "true",
        "LITELLM_LOG": "CRITICAL",
        "DEFAULT_MAX_RETRIES": "0",
        "HF_HUB_OFFLINE": "1",
    }.items():
        monkeypatch.setenv(name, value)
    for logger in ("LiteLLM", "LiteLLM Router", "LiteLLM Proxy", "openai", "httpx", "httpcore"):
        caplog.set_level(CRITICAL + 1, logger)

    adapter = LiteLLMEmbeddingAdapter(
        base_url=_CREDENTIAL.access.base_url,
        address=IPv4Address("127.0.0.1"),
        tls=create_default_context(),
        cipher=PyNaClProviderCredentialCipher(None, None, "f" * 64),
        approved_basis=_CALL.basis,
        approved_token_bound=_CALL.reviewed.effective.token_bound,
    )
    with pytest.raises(DependencyUnavailableError, match="callbacks are unavailable"):
        adapter.prepare()


@pytest.mark.asyncio
async def test_embedding_transport_rebuilds_request_and_sdk_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    from inframeld_backend.access.application.value_objects.provider_credential_value import (
        ProviderCredentialValue,
    )
    from inframeld_backend.shared.infrastructure.resources.bound_embedding_http_transport import (
        BoundEmbeddingHttpTransport,
    )

    request_body = {
        "model": "text-embedding-3-small",
        "input": [[31, 32]],
        "encoding_format": "float",
        "dimensions": 3,
    }
    safe_response = {
        "object": "list",
        "model": "text-embedding-3-small",
        "data": [{"object": "embedding", "index": 0, "embedding": [0.1, 0.2, 0.3]}],
        "usage": {"prompt_tokens": 2, "total_tokens": 2},
    }

    async def peer(_self: httpx.AsyncHTTPTransport, request: httpx.Request) -> httpx.Response:
        assert request.url.host == "127.0.0.1"
        assert request.headers["host"] == "fixture.example.test"
        assert request.headers["authorization"] == "Bearer fixture-key"
        assert "x-unapproved" not in request.headers
        return httpx.Response(
            200,
            request=request,
            headers={"x-unapproved": "provider-private-header", "x-request-id": "fixture-key"},
            stream=httpx.ByteStream(
                dumps({**safe_response, "private": "provider-private-body"}).encode()
            ),
        )

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", peer)
    transport = BoundEmbeddingHttpTransport(
        base_url="https://fixture.example.test/v1",
        address=IPv4Address("127.0.0.1"),
        tls=create_default_context(),
        model="text-embedding-3-small",
        tokens=(31, 32),
        dimensions=3,
        credential=ProviderCredentialValue("fixture-key"),
        dispatch_deadline=monotonic() + 5,
    )
    async with httpx.AsyncClient(transport=transport, trust_env=False) as sdk:
        response = await sdk.post(
            "https://fixture.example.test/v1/embeddings",
            json=request_body,
            headers={"Authorization": "Bearer dummy-sdk-key", "X-Unapproved": "ambient"},
        )

    assert response.json() == safe_response and "x-unapproved" not in response.headers
    assert transport.result is not None and transport.result.provider_reference is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "phase", ["tls-deadline", "header-deadline", "response", "refused", "untraced", "canceled"]
)
async def test_transport_tracks_header_admission_and_prewrite_evidence(
    monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    import httpx

    from inframeld_backend.access.application.value_objects.provider_credential_value import (
        ProviderCredentialValue,
    )
    from inframeld_backend.shared.infrastructure.resources.bound_embedding_http_transport import (
        BoundEmbeddingHttpTransport,
    )

    finish_reached = False

    async def peer(_self: httpx.AsyncHTTPTransport, request: httpx.Request) -> httpx.Response:
        nonlocal finish_reached
        trace = cast(
            Callable[[str, dict[str, object]], Awaitable[None]] | None,
            request.extensions.get("trace"),
        )
        if phase in ("refused", "untraced"):
            if trace is not None and phase == "refused":
                await trace("connection.connect_tcp.failed", {})
            raise httpx.ConnectError("Controlled connection failure.")
        if trace is not None:
            await trace("connection.start_tls.started", {})
        if phase == "canceled":
            raise asyncio.CancelledError
        if phase != "tls-deadline" and trace is not None:
            await trace("http11.send_request_headers.started", {})
            if phase == "response":
                await trace("http11.send_request_headers.complete", {})
        await asyncio.sleep(0.15)
        finish_reached = True
        return httpx.Response(503, request=request)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", peer)
    transport = BoundEmbeddingHttpTransport(
        base_url="https://fixture.example.test/v1",
        address=IPv4Address("127.0.0.1"),
        tls=create_default_context(),
        model="text-embedding-3-small",
        tokens=(31, 32),
        dimensions=3,
        credential=ProviderCredentialValue("fixture-key"),
        dispatch_deadline=monotonic() + 0.08,
    )
    request = httpx.Request(
        "POST",
        "https://fixture.example.test/v1/embeddings",
        json={
            "model": "text-embedding-3-small",
            "input": [[31, 32]],
            "encoding_format": "float",
            "dimensions": 3,
        },
        extensions={"timeout": {"connect": 2.0, "read": 2.0, "write": 2.0}},
    )

    async with transport:
        if phase == "response":
            assert (await transport.handle_async_request(request)).status_code == 503
            assert finish_reached
        else:
            expected = {
                "tls-deadline": TimeoutError,
                "header-deadline": TimeoutError,
                "refused": httpx.ConnectError,
                "untraced": httpx.ConnectError,
                "canceled": asyncio.CancelledError,
            }[phase]
            with pytest.raises(expected):
                await transport.handle_async_request(request)
            assert not finish_reached
    assert transport.not_sent == (phase in ("tls-deadline", "refused"))
