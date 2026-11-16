import asyncio
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from json import dumps
from math import isfinite
from time import monotonic
from uuid import uuid5

from inframeld_backend.access.application.services.model_dispatch_credential_service import (
    ModelDispatchCredentialService,
)
from inframeld_backend.shared.application.dtos.admitted_embedding_call_dto import (
    AdmittedEmbeddingCallDTO,
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
from inframeld_backend.shared.application.dtos.product_job_binding_dto import ProductJobBindingDTO
from inframeld_backend.shared.application.dtos.spending_call_context_dto import (
    SpendingCallContextDTO,
)
from inframeld_backend.shared.application.dtos.spending_observation_dto import (
    SpendingObservationDTO,
)
from inframeld_backend.shared.application.dtos.spending_usage_dto import SpendingUsageDTO
from inframeld_backend.shared.application.enums.spending_call_state import SpendingCallState
from inframeld_backend.shared.application.enums.spending_observation_kind import (
    SpendingObservationKind,
)
from inframeld_backend.shared.application.errors.application_errors import ConflictError
from inframeld_backend.shared.application.errors.job_errors import JobFenceLostError
from inframeld_backend.shared.application.protocols.model_dispatch_issuance_repository import (
    ModelDispatchIssuanceRepository,
)
from inframeld_backend.shared.application.protocols.model_embedding_adapter import (
    ModelEmbeddingAdapter,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.services.spending_accounting_service import (
    SpendingAccountingService,
)
from inframeld_backend.shared.application.value_objects.job_payload import JobPayload
from inframeld_backend.shared.application.value_objects.model_call_id import ModelCallId
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation

_KIND = "model.embed"
_PURPOSE = "model.embed.v1"
_UNKNOWN = EmbeddingDispatchResultDTO(SpendingObservationKind.UNCERTAIN)

type ModelDispatchPhase = tuple[
    TransactionManager,
    ModelDispatchCredentialService,
    SpendingAccountingService,
    ModelDispatchIssuanceRepository,
]


class ModelEmbeddingGateway:
    """Coordinate one original job-backed embedding invocation."""

    def __init__(
        self,
        open_phase: Callable[[], AbstractAsyncContextManager[ModelDispatchPhase]],
        adapter: ModelEmbeddingAdapter,
        fingerprints: RequestFingerprintService,
    ) -> None:
        self._open_phase = open_phase
        self._adapter = adapter
        self._fingerprints = fingerprints

    def admission_payload(self, call: AdmittedEmbeddingCallDTO) -> JobPayload:
        """Bind one fixed input and its conservative spending basis into durable admission."""
        RevisionValidation.require(call.access_revision)
        settings = self._settings(call)
        effective, selection, basis = call.reviewed.effective, call.reviewed.selection, call.basis
        if (
            not 1 <= settings.dimensions <= 1536
            or not 1 <= len(call.tokens) <= min(effective.context_tokens, 8191)
            or any(type(token) is not int or not 0 <= token < 2**31 for token in call.tokens)
            or basis.maximum_usage
            != (SpendingUsageDTO("input", "token", Decimal(len(call.tokens))),)
            or tuple((rate.category, rate.unit) for rate in basis.rates) != (("input", "token"),)
            or basis.rates[0].usd_per_unit <= 0
            or call.reviewed.price_overrides
        ):
            raise ConflictError("The original embedding settings or token bound is unsupported.")
        canonical = dumps(
            {
                "project": str(selection.project_id.value),
                "connection": str(selection.connection_id.value),
                "model": selection.model,
                "settings": asdict(effective),
                "reviewed_fingerprint": call.reviewed.fingerprint,
                "access_revision": call.access_revision,
                "tokens": call.tokens,
                "basis": (
                    basis.basis_id,
                    basis.source_reference,
                    basis.source_revision,
                    basis.captured_at.isoformat(),
                    str(basis.rates[0].usd_per_unit),
                ),
                "operation_limit": None
                if call.operation_limit is None
                else str(call.operation_limit.value),
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        return JobPayload(
            _KIND,
            1,
            self._fingerprints.fingerprint(purpose=_PURPOSE, canonical_request=canonical).value,
        )

    async def embed(
        self, attempt: JobAttemptContextDTO, call: AdmittedEmbeddingCallDTO
    ) -> EmbeddingDispatchResultDTO:
        """Dispatch only on a fresh commit acknowledged to this invocation."""
        payload = self.admission_payload(call)
        binding = attempt.binding
        selection = call.reviewed.selection
        if (
            not isinstance(binding, ProductJobBindingDTO)
            or selection.project_id != binding.authority.project_id
            or attempt.payload != payload
        ):
            raise ConflictError("The call differs from the original embedding work.")
        context = SpendingCallContextDTO(
            ModelCallId(
                uuid5(
                    binding.authority.installation_id.value,
                    f"{_PURPOSE}:{binding.operation_id.value}",
                )
            ),
            binding.operation_id,
            binding.authority,
            attempt,
            RequestFingerprint(payload.data),
        )
        self._adapter.prepare()
        async with (
            asyncio.timeout(5),
            self._open_phase() as (transactions, credentials, spending, issuances),
            transactions.begin(),
        ):
            credential = await credentials.read(
                attempt=attempt,
                connection_id=selection.connection_id,
                admitted_access_revision=call.access_revision,
            )
            adapter_revision = self._adapter.require_supported(call, credential)
            approval = await spending.prepare_new_dispatch_in_transaction(
                call=context, basis=call.basis, operation_limit=call.operation_limit
            )
            if (
                approval.recovered
                or approval.record.state is not SpendingCallState.ACCOUNTING_APPROVED
            ):
                raise ConflictError("The original model call did not receive fresh approval.")
            issuance = ModelDispatchIssuanceDTO(
                context.call_id,
                attempt.job_id,
                attempt.attempt,
                attempt.fence,
                selection.connection_id,
                credential.access_revision,
                credential.binding.revision,
                adapter_revision,
            )
            observed_before = monotonic()
            lease_remaining = await issuances.add(attempt, issuance)
        dispatch_deadline = observed_before + lease_remaining.total_seconds()
        if monotonic() >= dispatch_deadline:
            raise JobFenceLostError("The original lease expired before embedding dispatch.")

        result = await self._adapter.embed(call, credential, dispatch_deadline=dispatch_deadline)
        return await self._settle(context, issuance, approval.record.revision, call, result)

    @staticmethod
    def _settings(call: AdmittedEmbeddingCallDTO) -> EmbeddingModelSettingsDTO:
        settings = call.reviewed.effective.settings
        if not isinstance(settings, EmbeddingModelSettingsDTO):
            raise ConflictError("The original work does not select embedding settings.")
        return settings

    async def _settle(
        self,
        context: SpendingCallContextDTO,
        issuance: ModelDispatchIssuanceDTO,
        approval_revision: int,
        call: AdmittedEmbeddingCallDTO,
        result: EmbeddingDispatchResultDTO,
    ) -> EmbeddingDispatchResultDTO:
        vector, tokens = result.vector, result.prompt_tokens
        if result.kind is SpendingObservationKind.USAGE and (
            tokens is None
            or type(tokens) is not int
            or tokens != len(call.tokens)
            or vector is None
            or len(vector) != self._settings(call).dimensions
            or any(type(value) is not float or not isfinite(value) for value in vector)
        ):
            result = _UNKNOWN
        usage = (
            (SpendingUsageDTO("input", "token", Decimal(tokens)),)
            if result.kind is SpendingObservationKind.USAGE and tokens is not None
            else None
        )
        evidence = SpendingObservationDTO(
            uuid5(context.call_id.value, "embedding-adapter-observation"),
            context.call_id,
            result.kind,
            datetime.now(UTC),
            result.provider_reference or "original-embedding-adapter",
            usage=usage,
        )
        async with (
            asyncio.timeout(5),
            self._open_phase() as (transactions, _, spending, issuances),
            transactions.begin(),
        ):
            if await issuances.get(context.call_id) != issuance:
                raise ConflictError("The observation differs from the original issued work.")
            accounting = await spending.record_observation_in_transaction(
                call=context, observation=evidence, expected_call_revision=approval_revision
            )
            if accounting.pending:
                return _UNKNOWN
            if result.kind is SpendingObservationKind.UNCERTAIN:
                return result
            checkpoint = (
                b""
                if result.kind is SpendingObservationKind.NOT_SENT
                else dumps(
                    {"call_id": str(context.call_id.value), "vector": result.vector},
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode()
            )
            confirmed = await issuances.confirm(context.attempt, context.call_id, checkpoint)
        return result if confirmed else _UNKNOWN
