import asyncio
from collections.abc import Awaitable, Callable
from ipaddress import IPv4Address, IPv6Address
from logging import CRITICAL, Logger, getLogger
from os import getenv
from ssl import CERT_REQUIRED, SSLContext
from typing import cast, override

import httpx
import openai

from inframeld_backend.access.application.dtos.model_dispatch_credential_dto import (
    ModelDispatchCredentialDTO,
)
from inframeld_backend.access.domain.enums.model_connection_provider import ModelConnectionProvider
from inframeld_backend.access.infrastructure.resources.pynacl_provider_credential_cipher import (
    PyNaClProviderCredentialCipher,
)
from inframeld_backend.shared.application.dtos.admitted_embedding_call_dto import (
    AdmittedEmbeddingCallDTO,
)
from inframeld_backend.shared.application.dtos.captured_spending_basis_dto import (
    CapturedSpendingBasisDTO,
)
from inframeld_backend.shared.application.dtos.embedding_dispatch_result_dto import (
    EmbeddingDispatchResultDTO,
)
from inframeld_backend.shared.application.dtos.embedding_model_settings_dto import (
    EmbeddingModelSettingsDTO,
)
from inframeld_backend.shared.application.dtos.model_token_bound_dto import ModelTokenBoundDTO
from inframeld_backend.shared.application.enums.embedding_normalization import (
    EmbeddingNormalization,
)
from inframeld_backend.shared.application.enums.spending_observation_kind import (
    SpendingObservationKind,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.protocols.model_embedding_adapter import (
    ModelEmbeddingAdapter,
)
from inframeld_backend.shared.infrastructure.resources.bound_embedding_http_transport import (
    BoundEmbeddingHttpTransport,
)

_ADAPTER_REVISION = "litellm-core-1.108.3/openai-2.54.0/embedding-v1"
_MODEL = "text-embedding-3-small"
_SDK_TOKEN = "inframeld-bound-transport"
_OFFLINE_PROFILE = {
    "LITELLM_MODE": "PRODUCTION",
    "LITELLM_LOCAL_MODEL_COST_MAP": "True",
    "LITELLM_TELEMETRY_DISABLED": "true",
    "LITELLM_LOG": "CRITICAL",
    "DEFAULT_MAX_RETRIES": "0",
    "HF_HUB_OFFLINE": "1",
}

_CALLBACK_COLLECTIONS = (
    "callbacks",
    "input_callback",
    "success_callback",
    "failure_callback",
    "service_callback",
    "audit_log_callbacks",
    "batch_line_item_callbacks",
    "_async_input_callback",
    "_async_success_callback",
    "_async_failure_callback",
    "pre_call_rules",
    "post_call_rules",
)


class LiteLLMEmbeddingAdapter(ModelEmbeddingAdapter):
    """Execute one OpenAI-compatible embedding over a fixed, controlled TLS route."""

    def __init__(
        self,
        *,
        base_url: str,
        address: IPv4Address | IPv6Address,
        tls: SSLContext,
        cipher: PyNaClProviderCredentialCipher,
        approved_basis: CapturedSpendingBasisDTO,
        approved_token_bound: ModelTokenBoundDTO,
    ) -> None:
        self._base_url = base_url
        self._address = address
        self._tls = tls
        self._cipher = cipher
        self._approved_basis = approved_basis
        self._approved_token_bound = approved_token_bound

    @override
    def prepare(self) -> None:
        self._sdk_entry()

    @override
    def require_supported(
        self, call: AdmittedEmbeddingCallDTO, credential: ModelDispatchCredentialDTO
    ) -> str:
        settings = call.reviewed.effective.settings
        if (
            credential.access.provider is not ModelConnectionProvider.OPENAI_COMPATIBLE
            or credential.access.base_url != self._base_url
            or credential.access.api_version is not None
            or call.reviewed.selection.model != _MODEL
            or not isinstance(settings, EmbeddingModelSettingsDTO)
            or settings.expected_provider != ModelConnectionProvider.OPENAI_COMPATIBLE.value
            or settings.expected_model_revision is not None
            or settings.normalization is not EmbeddingNormalization.NONE
            or call.reviewed.effective.token_bound != self._approved_token_bound
            or call.basis != self._approved_basis
            or not self._address.is_loopback
            or self._tls.verify_mode != CERT_REQUIRED
            or not self._tls.check_hostname
        ):
            raise ConflictError("The admitted embedding route, model or pricing is unsupported.")
        self._require_offline_profile()
        return _ADAPTER_REVISION

    @override
    async def embed(
        self,
        call: AdmittedEmbeddingCallDTO,
        credential: ModelDispatchCredentialDTO,
        *,
        dispatch_deadline: float,
    ) -> EmbeddingDispatchResultDTO:
        try:
            embed = self._sdk_entry()
        except DependencyUnavailableError:
            return EmbeddingDispatchResultDTO(SpendingObservationKind.NOT_SENT)

        settings = call.reviewed.effective.settings
        if not isinstance(settings, EmbeddingModelSettingsDTO):
            raise ConflictError("The original call requires bounded embedding settings.")
        try:
            key = self._cipher.decrypt(credential.envelope, credential.binding)
        except DependencyUnavailableError:
            return EmbeddingDispatchResultDTO(SpendingObservationKind.NOT_SENT)

        route = BoundEmbeddingHttpTransport(
            base_url=self._base_url,
            address=self._address,
            tls=self._tls,
            model=_MODEL,
            tokens=call.tokens,
            dimensions=settings.dimensions,
            credential=key,
            dispatch_deadline=dispatch_deadline,
        )
        async with (
            httpx.AsyncClient(
                transport=route,
                trust_env=False,
                follow_redirects=False,
                timeout=2.0,
            ) as client,
            openai.AsyncOpenAI(
                base_url=self._base_url,
                api_key=_SDK_TOKEN,
                http_client=client,
                max_retries=0,
                timeout=2.0,
            ) as sdk,
        ):
            try:
                async with asyncio.timeout(4):
                    await embed(
                        model=_MODEL,
                        custom_llm_provider="openai",
                        input=[list(call.tokens)],
                        dimensions=settings.dimensions,
                        encoding_format="float",
                        api_base=self._base_url,
                        api_key=_SDK_TOKEN,
                        client=sdk,
                        max_retries=0,
                        num_retries=0,
                        timeout=2.0,
                        **{"no-log": True},
                    )
                    if sdk.max_retries != 0:
                        raise ValueError("The embedding SDK changed its retry profile.")
            except (openai.OpenAIError, httpx.HTTPError, TimeoutError, ValueError):
                return EmbeddingDispatchResultDTO(
                    SpendingObservationKind.NOT_SENT
                    if route.not_sent
                    else SpendingObservationKind.UNCERTAIN,
                    response_status=route.response_status,
                )
        return route.result or EmbeddingDispatchResultDTO(
            SpendingObservationKind.UNCERTAIN, response_status=route.response_status
        )

    @staticmethod
    def _sdk_entry() -> Callable[..., Awaitable[object]]:
        LiteLLMEmbeddingAdapter._require_offline_profile()

        # The pinned SDK is imported only under the offline process profile, outside SQL.
        import litellm

        if getattr(litellm, "DEFAULT_MAX_RETRIES", None) != 0:
            raise DependencyUnavailableError("The embedding SDK retry profile is unavailable.")
        if getattr(litellm, "global_disable_no_log_param", None) is not False or any(
            getattr(litellm, name, None) not in ([], ()) for name in _CALLBACK_COLLECTIONS
        ):
            raise DependencyUnavailableError("The embedding SDK callbacks are unavailable.")

        # Check the effective logger state as the environment is only an import-time input.
        logger_names = ("LiteLLM", "LiteLLM Router", "LiteLLM Proxy", "openai", "httpx", "httpcore")
        loggers = [getLogger(name) for name in logger_names]
        loggers.extend(
            logger
            for name, logger in Logger.manager.loggerDict.copy().items()
            if isinstance(logger, Logger)
            and name.startswith(tuple(f"{root}." for root in logger_names))
        )
        if getattr(litellm, "set_verbose", None) is not False or any(
            logger.isEnabledFor(CRITICAL) for logger in loggers
        ):
            raise DependencyUnavailableError("The embedding SDK logging profile is unavailable.")

        embedding = getattr(litellm, "aembedding", None)
        if not callable(embedding):
            raise DependencyUnavailableError("The qualified embedding SDK entry is unavailable.")
        return cast(Callable[..., Awaitable[object]], embedding)

    @staticmethod
    def _require_offline_profile() -> None:
        if any(getenv(name) != value for name, value in _OFFLINE_PROFILE.items()):
            raise DependencyUnavailableError("The embedding SDK offline profile is unavailable.")
