import asyncio
import os
from asyncio import StreamReader, StreamWriter
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from importlib import import_module
from ipaddress import IPv4Address
from json import dumps, loads
from logging import CRITICAL
from pathlib import Path
from ssl import PROTOCOL_TLS_SERVER, SSLContext, create_default_context
from uuid import uuid4, uuid5

import pytest
import trustme
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.support.spending_scenarios import (
    SpendingScenarioDTO,
    change_limit,
    finish_fixture_job,
    seed_spending_scenario,
)

from inframeld_backend.access.application.commands.change_model_connection_credential_command import (
    ChangeModelConnectionCredentialCommand,
)
from inframeld_backend.access.application.commands.create_model_connection_command import (
    CreateModelConnectionCommand,
)
from inframeld_backend.access.application.dtos.model_connection_access_dto import (
    ModelConnectionAccessDTO,
)
from inframeld_backend.access.application.services.action_authorization_service import (
    ActionAuthorizationService,
)
from inframeld_backend.access.application.services.admitted_work_authorization_service import (
    AdmittedWorkAuthorizationService,
)
from inframeld_backend.access.application.value_objects.provider_credential_value import (
    ProviderCredentialValue,
)
from inframeld_backend.access.domain.enums.model_connection_authentication import (
    ModelConnectionAuthentication,
)
from inframeld_backend.access.domain.enums.model_connection_provider import ModelConnectionProvider
from inframeld_backend.access.domain.policies.model_connection_destination_policy import (
    ModelConnectionDestinationPolicy,
)
from inframeld_backend.access.infrastructure.readers.postgres_admitted_work_facts_reader import (
    PostgresAdmittedWorkFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_action_facts_reader import (
    PostgresProjectActionFactsReader,
)
from inframeld_backend.access.infrastructure.resources.pynacl_provider_credential_cipher import (
    PyNaClProviderCredentialCipher,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.settings.model_connection_destination_settings import (
    ModelConnectionDestinationSettings,
)
from inframeld_backend.access.infrastructure.settings.provider_credential_settings import (
    ProviderCredentialSettings,
)
from inframeld_backend.access.infrastructure.writers.postgres_job_admission_audit_writer import (
    PostgresJobAdmissionAuditWriter,
)
from inframeld_backend.bootstrap.model_connection_composition import (
    open_model_connection_creation,
    open_model_connection_credentials,
)
from inframeld_backend.bootstrap.model_gateway_composition import build_model_embedding_gateway
from inframeld_backend.bootstrap.spending_accounting_composition import open_spending_accounting
from inframeld_backend.shared.application.dtos.admitted_embedding_call_dto import (
    AdmittedEmbeddingCallDTO,
)
from inframeld_backend.shared.application.dtos.captured_spending_basis_dto import (
    CapturedSpendingBasisDTO,
)
from inframeld_backend.shared.application.dtos.effective_model_settings_dto import (
    EffectiveModelSettingsDTO,
)
from inframeld_backend.shared.application.dtos.embedding_model_settings_dto import (
    EmbeddingModelSettingsDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.dtos.model_selection_dto import ModelSelectionDTO
from inframeld_backend.shared.application.dtos.model_token_bound_dto import ModelTokenBoundDTO
from inframeld_backend.shared.application.dtos.product_job_binding_dto import ProductJobBindingDTO
from inframeld_backend.shared.application.dtos.reviewed_model_settings_dto import (
    ReviewedModelSettingsDTO,
)
from inframeld_backend.shared.application.dtos.spending_call_context_dto import (
    SpendingCallContextDTO,
)
from inframeld_backend.shared.application.dtos.spending_rate_dto import SpendingRateDTO
from inframeld_backend.shared.application.dtos.spending_usage_dto import SpendingUsageDTO
from inframeld_backend.shared.application.enums.embedding_distance import EmbeddingDistance
from inframeld_backend.shared.application.enums.embedding_normalization import (
    EmbeddingNormalization,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.model_role import ModelRole
from inframeld_backend.shared.application.enums.model_token_bound_kind import ModelTokenBoundKind
from inframeld_backend.shared.application.enums.spending_call_state import SpendingCallState
from inframeld_backend.shared.application.enums.spending_observation_kind import (
    SpendingObservationKind,
)
from inframeld_backend.shared.application.errors.application_errors import ConflictError
from inframeld_backend.shared.application.errors.spending_errors import SpendingLimitExceededError
from inframeld_backend.shared.application.services.artifact_cleanup_authorization_service import (
    ArtifactCleanupAuthorizationService,
)
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.application.services.job_admission_service import JobAdmissionService
from inframeld_backend.shared.application.services.job_continuation_eligibility_service import (
    JobContinuationEligibilityService,
)
from inframeld_backend.shared.application.services.job_execution_service import JobExecutionService
from inframeld_backend.shared.application.services.job_recovery_service import JobRecoveryService
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.job_payload import JobPayload
from inframeld_backend.shared.application.value_objects.model_call_id import ModelCallId
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.enums.job_status import JobStatus
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)
from inframeld_backend.shared.domain.value_objects.usd_amount import UsdAmount
from inframeld_backend.shared.infrastructure.readers.postgres_artifact_cleanup_facts_reader import (
    PostgresArtifactCleanupFactsReader,
)
from inframeld_backend.shared.infrastructure.repositories.postgres_job_store import PostgresJobStore
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow
from inframeld_backend.shared.infrastructure.rows.model_call_accounting_evidence_row import (
    ModelCallAccountingEvidenceRow,
)
from inframeld_backend.shared.infrastructure.rows.model_call_accounting_row import (
    ModelCallAccountingRow,
)
from inframeld_backend.shared.infrastructure.rows.model_dispatch_issuance_row import (
    ModelDispatchIssuanceRow,
)
from inframeld_backend.shared.infrastructure.rows.project_spending_policy_row import (
    ProjectSpendingPolicyRow,
)
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1", reason="Requires isolated PostgreSQL"
    ),
]

_HOSTNAME = "embeddings.fixture.test"
_MODEL = "text-embedding-3-small"
_ADDRESS = IPv4Address("127.0.0.1")
_KEY = "controlled-provider-key"
_FINGERPRINT_KEY = RequestFingerprintKey(b"F" * 32)
_FINGERPRINTS = RequestFingerprintService(_FINGERPRINT_KEY)
_VECTOR = (0.125, 0.25, -0.5)


async def _admit(
    database: Database, owner: SpendingScenarioDTO, payload: JobPayload
) -> JobAttemptContextDTO:
    binding = owner.attempt.binding
    assert isinstance(binding, ProductJobBindingDTO)
    supported = ((payload.kind, payload.version),)
    async with database.session() as session, session.begin():
        await JobAdmissionService(
            ActionAuthorizationService(PostgresProjectActionFactsReader(session)),
            AdmittedWorkAuthorizationService(PostgresAdmittedWorkFactsReader(session)),
            IdempotencyService(PostgresOperationReservationWriter(session)),
            PostgresJobStore(session),
            PostgresJobAdmissionAuditWriter(session),
            supported_payloads=supported,
        ).admit(
            access=owner.access,
            authority=binding.authority,
            context=IdempotencyContextDTO(
                HttpMethod.POST,
                "/v1/projects/{project_id}/sources",
                IdempotencyKey("embed-fixture"),
            ),
            fingerprint=RequestFingerprint(payload.data),
            request_id=RequestId(uuid4()),
            payload=payload,
        )

    async with database.session() as session:
        jobs = PostgresJobStore(session)
        authority = AdmittedWorkAuthorizationService(PostgresAdmittedWorkFactsReader(session))
        attempt = await JobExecutionService(
            SqlAlchemyTransactionManager(session),
            jobs,
            supported_payloads=supported,
            worker_id=uuid4(),
            admitted_work_authorizer=authority,
            job_recovery=JobRecoveryService(
                jobs,
                JobContinuationEligibilityService(
                    jobs,
                    authority,
                    ArtifactCleanupAuthorizationService(
                        PostgresArtifactCleanupFactsReader(session)
                    ),
                    supported_payloads=supported,
                ),
            ),
        ).claim_next()
    assert attempt is not None and attempt.payload == payload
    return attempt


@pytest.mark.parametrize(
    "outcome",
    [
        "accepted",
        "lost",
        "late",
        "canceled",
        "invalid",
        "redirect",
        "missing-key",
        "legacy",
        "cap",
        "issue-conflict",
        "rollback",
    ],
)
async def test_original_model_embedding_uses_committed_issuance_and_exact_wire_evidence(
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    outcome: str,
) -> None:
    from inframeld_backend.shared.infrastructure.resources.litellm_embedding_adapter import (
        LiteLLMEmbeddingAdapter,
    )

    owner = await seed_spending_scenario(database)
    await finish_fixture_job(database, owner)
    attempt: JobAttemptContextDTO | None = None
    requests = 0
    names: list[str | None] = []
    handlers: list[asyncio.Task[None]] = []
    open_sessions = 0
    open_session = database.session

    @asynccontextmanager
    async def tracked_session() -> AsyncGenerator[AsyncSession]:
        nonlocal open_sessions
        open_sessions += 1
        try:
            async with open_session() as session:
                yield session
        finally:
            open_sessions -= 1

    monkeypatch.setattr(database, "session", tracked_session)

    ca = trustme.CA()
    peer_tls = SSLContext(PROTOCOL_TLS_SERVER)
    leaf = ca.issue_cert(_HOSTNAME)
    certificate_path, private_path, ca_path = (
        tmp_path / "peer.pem",
        tmp_path / "peer.key",
        tmp_path / "ca.pem",
    )
    leaf.cert_chain_pems[0].write_to_path(certificate_path)
    leaf.private_key_pem.write_to_path(private_path)
    private_path.chmod(0o600)
    ca.cert_pem.write_to_path(ca_path)
    peer_tls.load_cert_chain(certificate_path, private_path)
    peer_tls.sni_callback = lambda _socket, name, _context: names.append(name)
    client_tls = create_default_context(cafile=ca_path)
    for key, value in {
        "LITELLM_MODE": "PRODUCTION",
        "LITELLM_LOCAL_MODEL_COST_MAP": "True",
        "LITELLM_TELEMETRY_DISABLED": "true",
        "LITELLM_LOG": "CRITICAL",
        "DEFAULT_MAX_RETRIES": "0",
        "HF_HUB_OFFLINE": "1",
        "OPENAI_API_KEY": "ambient-unapproved-key",
        "OPENAI_ORG_ID": "ambient-unapproved-org",
        "OPENAI_CUSTOM_HEADERS": "X-Unapproved: test-secret-header",
        "OPENAI_BASE_URL": "http://127.0.0.1:1/fallback",
        "HTTPS_PROXY": "http://127.0.0.1:1",
    }.items():
        monkeypatch.setenv(key, value)
    # LiteLLM sets the HTTPX logger level during import.
    import_module("litellm")
    for logger in ("LiteLLM", "LiteLLM Router", "LiteLLM Proxy", "openai", "httpx", "httpcore"):
        caplog.set_level(CRITICAL + 1, logger)

    async def serve(reader: StreamReader, writer: StreamWriter) -> None:
        nonlocal requests
        try:
            async with asyncio.timeout(3):
                line, *rest = (await reader.readuntil(b"\r\n\r\n")).split(b"\r\n")
                headers = dict(
                    (name.lower(), value.strip())
                    for name, value in (part.split(b":", 1) for part in rest if part)
                )
                body = loads(await reader.readexactly(int(headers[b"content-length"])))
                requests += 1
                assert line == b"POST /v1/embeddings HTTP/1.1"
                assert headers[b"host"] == f"{_HOSTNAME}:{port}".encode()
                assert headers.get(b"authorization") == f"Bearer {_KEY}".encode()
                assert (
                    not {b"openai-organization", b"x-unapproved", b"proxy-authorization"}
                    & headers.keys()
                )
                assert body == {
                    "model": _MODEL,
                    "input": [[31, 32]],
                    "dimensions": 3,
                    "encoding_format": "float",
                }
                assert attempt is not None
                assert open_sessions == 0, (
                    "The provider started before the database session closed."
                )

                # An independent session can acquire every coordination lock at wire entry.
                async with database.session() as observer, observer.begin():
                    assert (
                        await observer.get(
                            ProjectRow, owner.project_id.value, with_for_update={"nowait": True}
                        )
                        is not None
                    )
                    job = await observer.get(
                        DurableJobRow, attempt.job_id.value, with_for_update={"nowait": True}
                    )
                    assert (
                        await observer.get(
                            ProjectSpendingPolicyRow,
                            owner.project_id.value,
                            with_for_update={"nowait": True},
                        )
                        is not None
                    )
                    issuance = await observer.scalar(
                        select(ModelDispatchIssuanceRow).where(
                            ModelDispatchIssuanceRow.job_id == attempt.job_id.value
                        )
                    )
                    assert issuance is not None and issuance.fence == attempt.fence.value
                    assert (
                        job is not None and job.pending_effect == f"model-call:{issuance.call_id}"
                    )
                    accounting = await observer.get(
                        ModelCallAccountingRow, issuance.call_id, with_for_update={"nowait": True}
                    )
                    assert (
                        accounting is not None
                        and accounting.state == SpendingCallState.ACCOUNTING_APPROVED
                    )
                    if outcome == "late":
                        job.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
                    if outcome == "canceled":
                        await PostgresJobStore(observer).request_cancel(attempt.job_id)
                    if outcome == "rollback":
                        job.checkpoint = b"conflicting-job-progress"
                if outcome == "redirect":
                    writer.write(
                        b"HTTP/1.1 307 Temporary Redirect\r\nContent-Length: 0\r\n"
                        + f"Location: {base}/wrong\r\nConnection: close\r\n\r\n".encode()
                    )
                    await writer.drain()
                elif outcome != "lost":
                    vector = ["0.125", 0.25, -0.5] if outcome == "invalid" else _VECTOR
                    result = dumps(
                        {
                            "object": "list",
                            "model": _MODEL,
                            "data": [{"object": "embedding", "index": 0, "embedding": vector}],
                            "usage": {"prompt_tokens": 2, "total_tokens": 2},
                        }
                    ).encode()
                    writer.write(
                        b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                        + f"Content-Length: {len(result)}\r\nx-request-id: native-fixture-call\r\n".encode()
                        + b"Connection: close\r\n\r\n"
                        + result
                    )
                    await writer.drain()
        finally:
            writer.close()
            with suppress(OSError, TimeoutError):
                async with asyncio.timeout(2):
                    await writer.wait_closed()

    def on_connection(reader: StreamReader, writer: StreamWriter) -> None:
        handlers.append(asyncio.create_task(serve(reader, writer)))

    server = await asyncio.start_server(
        on_connection, str(_ADDRESS), 0, ssl=peer_tls, ssl_handshake_timeout=2
    )
    port = server.sockets[0].getsockname()[1]
    base = f"https://{_HOSTNAME}:{port}/v1"
    destinations = ModelConnectionDestinationSettings(https_base_urls=frozenset({base}))
    connection_path = f"/v1/projects/{owner.project_id.value}/model-connections"
    try:
        async with server:
            async with open_model_connection_creation(
                database, _FINGERPRINTS, destinations
            ) as creator:
                created = await creator.create(
                    access=owner.access,
                    command=CreateModelConnectionCommand(
                        owner.project_id,
                        ResourceName("fixture-embeddings"),
                        SubmittedDisplayName("Fixture embeddings"),
                        ModelConnectionAccessDTO(
                            ModelConnectionProvider.OPENAI_COMPATIBLE,
                            base,
                            None,
                            ModelConnectionAuthentication.API_KEY,
                        ),
                    ),
                    context=IdempotencyContextDTO(
                        HttpMethod.POST, connection_path, IdempotencyKey("create-fixture")
                    ),
                )
            selected = created.connection.connection_id
            credential_path = f"{connection_path}/{selected.value}/credential"
            root = bytes(range(32))
            key_file = tmp_path / "provider.key"
            key_file.write_bytes(root)
            key_file.chmod(0o600)
            key_id = sha256(root).hexdigest()
            async with open_model_connection_credentials(
                database,
                _FINGERPRINT_KEY,
                destinations,
                ProviderCredentialSettings(key_file=key_file, expected_key_id=key_id),
            ) as credentials:
                await credentials.change(
                    owner.access,
                    ChangeModelConnectionCredentialCommand(
                        owner.project_id, selected, 0, ProviderCredentialValue(_KEY)
                    ),
                    IdempotencyContextDTO(
                        HttpMethod.PUT, credential_path, IdempotencyKey("fixture-key")
                    ),
                )

            bound = ModelTokenBoundDTO(ModelTokenBoundKind.EXACT, "controlled-input-tokens", "v1")
            basis = CapturedSpendingBasisDTO(
                "one-fixture-embedding",
                "controlled native endpoint",
                "v1",
                datetime.now(UTC),
                (SpendingRateDTO("input", "token", Decimal("0.1")),),
                (SpendingUsageDTO("input", "token", Decimal(2)),),
            )
            call = AdmittedEmbeddingCallDTO(
                ReviewedModelSettingsDTO(
                    ModelSelectionDTO(owner.project_id, selected, _MODEL, ModelRole.EMBEDDING),
                    EffectiveModelSettingsDTO(
                        8191,
                        bound,
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
                    "native-reviewed-embedding",
                ),
                created.connection.connection_access_revision,
                (31, 32),
                basis,
                UsdAmount(Decimal("1")),
            )
            adapter = LiteLLMEmbeddingAdapter(
                base_url=base,
                address=_ADDRESS,
                tls=client_tls,
                cipher=PyNaClProviderCredentialCipher(
                    key_file, key_id, sha256(_FINGERPRINT_KEY.value).hexdigest()
                ),
                approved_basis=basis,
                approved_token_bound=bound,
            )
            gateway = build_model_embedding_gateway(
                database,
                adapter,
                ModelConnectionDestinationPolicy(destinations.https_base_urls),
                _FINGERPRINTS,
            )
            attempt = await _admit(database, owner, gateway.admission_payload(call))
            if outcome == "issue-conflict":
                async with database.session() as session, session.begin():
                    job = await session.get(DurableJobRow, attempt.job_id.value)
                    assert job is not None
                    job.checkpoint = b"already-recorded-work"
                with pytest.raises(ConflictError, match="already has progress"):
                    await gateway.embed(attempt, call)
                assert requests == 0 and not names
                async with database.session() as session:
                    assert await session.scalar(select(ModelCallAccountingRow)) is None
                    assert await session.scalar(select(ModelDispatchIssuanceRow)) is None
                return
            if outcome == "missing-key":
                key_file.unlink()
            if outcome in ("legacy", "cap"):
                binding = attempt.binding
                assert isinstance(binding, ProductJobBindingDTO)
                spending_call = SpendingCallContextDTO(
                    ModelCallId(
                        uuid5(
                            binding.authority.installation_id.value,
                            f"model.embed.v1:{binding.operation_id.value}",
                        )
                    ),
                    binding.operation_id,
                    binding.authority,
                    attempt,
                    RequestFingerprint(attempt.payload.data),
                )
                async with open_spending_accounting(database) as accountant:
                    reserved = await accountant.reserve(
                        call=spending_call, basis=basis, operation_limit=call.operation_limit
                    )
                    if outcome == "legacy":
                        await accountant.approve_accounting(
                            call=spending_call, expected_call_revision=reserved.record.revision
                        )
                if outcome == "cap":
                    await change_limit(database, owner, UsdAmount(Decimal("0.1")))
                expected = SpendingLimitExceededError if outcome == "cap" else ConflictError
                with pytest.raises(expected):
                    await gateway.embed(attempt, call)
                assert requests == 0 and not names
                async with database.session() as observer:
                    row = await observer.get(ModelCallAccountingRow, spending_call.call_id.value)
                    job = await observer.get(DurableJobRow, attempt.job_id.value)
                    assert row is not None and row.hold_amount == Decimal("0.2")
                    assert row.state == (
                        SpendingCallState.RESERVED
                        if outcome == "cap"
                        else SpendingCallState.ACCOUNTING_APPROVED
                    )
                    assert job is not None and job.pending_effect is None
                    assert (
                        await observer.get(ModelDispatchIssuanceRow, spending_call.call_id.value)
                        is None
                    )
                return
            if outcome == "rollback":
                with pytest.raises(ConflictError, match="changed before confirmation"):
                    await gateway.embed(attempt, call)
                assert requests == 1 and names == [_HOSTNAME]
                async with database.session() as observer:
                    issuance = await observer.scalar(select(ModelDispatchIssuanceRow))
                    assert issuance is not None
                    row = await observer.get(ModelCallAccountingRow, issuance.call_id)
                    assert row is not None and row.state == SpendingCallState.ACCOUNTING_APPROVED
                    assert row.settled_amount is None and row.hold_amount == Decimal("0.2")
                    assert await observer.scalar(select(ModelCallAccountingEvidenceRow)) is None
                    job = await observer.get(DurableJobRow, attempt.job_id.value)
                    assert (
                        job is not None and job.pending_effect == f"model-call:{issuance.call_id}"
                    )
                    assert job.checkpoint == b"conflicting-job-progress"
                return
            result = await gateway.embed(attempt, call)
            if outcome not in ("late", "canceled"):
                with pytest.raises(ConflictError):
                    await gateway.embed(attempt, call)
    finally:
        await asyncio.gather(*handlers)

    if outcome == "missing-key":
        assert requests == 0 and not names
    else:
        assert requests == 1 and names == [_HOSTNAME]
    assert attempt is not None
    async with database.session() as session, session.begin():
        issuance = await session.scalar(select(ModelDispatchIssuanceRow))
        job = await session.get(DurableJobRow, attempt.job_id.value)
        assert issuance is not None and job is not None
        accounting = await session.get(ModelCallAccountingRow, issuance.call_id)
        assert accounting is not None
        assert issuance.connection_id == selected.value
        assert (
            issuance.credential_revision == 1 and issuance.access_revision == call.access_revision
        )
        if outcome == "accepted":
            assert result.vector == _VECTOR and result.provider_reference == "native-fixture-call"
            assert accounting.settled_amount == Decimal("0.2") and accounting.hold_amount == 0
            assert accounting.state == SpendingCallState.SETTLED and job.pending_effect is None
            assert loads(job.checkpoint)["vector"] == list(_VECTOR)
        elif outcome == "canceled":
            assert result.vector is None
            assert accounting.state == SpendingCallState.SETTLED
            assert accounting.settled_amount == Decimal("0.2") and accounting.hold_amount == 0
            assert job.cancel_requested and job.pending_effect is None and job.checkpoint == b""
        elif outcome == "missing-key":
            assert result.kind is SpendingObservationKind.NOT_SENT and result.vector is None
            assert accounting.state == SpendingCallState.RELEASED
            assert (
                accounting.hold_amount == 0 and job.pending_effect is None and job.checkpoint == b""
            )
        else:
            assert result.kind is SpendingObservationKind.UNCERTAIN and result.vector is None
            if outcome == "redirect":
                assert result.response_status == 307
            assert accounting.settled_amount is None and accounting.hold_amount == Decimal("0.2")
            assert job.pending_effect == f"model-call:{issuance.call_id}" and job.checkpoint == b""
            if outcome == "late":
                evidence = await session.scalar(select(ModelCallAccountingEvidenceRow))
                assert evidence is not None and evidence.applied_state is None
                assert accounting.state == SpendingCallState.ACCOUNTING_APPROVED
            else:
                assert accounting.state == SpendingCallState.UNRESOLVED
                await PostgresJobStore(session).finish(
                    attempt, status=JobStatus.FAILED, reason="fixture-loss"
                )
                assert job.status == JobStatus.RECOVERY_REQUIRED
