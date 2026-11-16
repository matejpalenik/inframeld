import os
import stat
from base64 import b64decode, b64encode
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
from typing import ClassVar

from inframeld_backend.access.domain.enums.model_connection_provider import ModelConnectionProvider
from inframeld_backend.shared.application.dtos.embedding_model_settings_dto import (
    EmbeddingModelSettingsDTO,
)
from inframeld_backend.shared.application.dtos.model_token_bound_dto import ModelTokenBoundDTO
from inframeld_backend.shared.application.dtos.reviewed_model_settings_dto import (
    ReviewedModelSettingsDTO,
)
from inframeld_backend.shared.application.enums.model_role import ModelRole
from inframeld_backend.shared.application.enums.model_token_bound_kind import ModelTokenBoundKind
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
    InvalidInputError,
)

_CL100K_BYTES = 1_681_126
_CL100K_RANKS = 100_256
_CL100K_SHA256 = "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7"
_TIKTOKEN_VERSION = "0.14.0"
_MODEL_MAX_TOKENS = 8_191

# OpenAI's cl100k_base recipe from tiktoken 0.14.0, tiktoken_ext/openai_public.py.
_CL100K_PATTERN = (
    r"'(?i:[sdmt]|ll|ve|re)|[^\r\n\p{L}\p{N}]?+\p{L}++|\p{N}{1,3}+"
    r"| ?[^\s\p{L}\p{N}]++[\r\n]*+|\s++$|\s*[\r\n]|\s+(?!\S)|\s"
)
_CL100K_SPECIAL_TOKENS = {
    "<|endoftext|>": 100_257,
    "<|fim_prefix|>": 100_258,
    "<|fim_middle|>": 100_259,
    "<|fim_suffix|>": 100_260,
    "<|endofprompt|>": 100_276,
}


class OpenAIEmbeddingTokenizer:
    """Prepare immutable inputs with the pinned offline text-embedding-3-small recipe."""

    token_bound: ClassVar[ModelTokenBoundDTO] = ModelTokenBoundDTO(
        ModelTokenBoundKind.EXACT,
        "tiktoken/cl100k_base",
        f"{_TIKTOKEN_VERSION}:sha256:{_CL100K_SHA256}",
    )

    def __init__(self, asset_path: Path) -> None:
        try:
            if version("tiktoken") != _TIKTOKEN_VERSION:
                raise ValueError("Tokenizer version mismatch.")
            from tiktoken import Encoding

            ranks = self._read_ranks(asset_path)
            self._encoding = Encoding(
                "cl100k_base",
                pat_str=_CL100K_PATTERN,
                mergeable_ranks=ranks,
                special_tokens=_CL100K_SPECIAL_TOKENS,
            )
        except (ImportError, OSError, ValueError):
            raise DependencyUnavailableError(
                "The pinned OpenAI embedding tokenizer is unavailable."
            ) from None
        self._max_token_bytes = max(map(len, ranks))

    def document_tokens(
        self,
        text: str,
        *,
        reviewed: ReviewedModelSettingsDTO,
        provider: ModelConnectionProvider,
    ) -> tuple[int, ...]:
        """Tokenize the exact saved document prefix and document text together."""
        settings = self._require_supported(reviewed, provider)
        return self._encode(text, settings.document_prefix, reviewed.effective.context_tokens)

    def query_tokens(
        self,
        text: str,
        *,
        reviewed: ReviewedModelSettingsDTO,
        provider: ModelConnectionProvider,
    ) -> tuple[int, ...]:
        """Tokenize the exact saved query prefix and query text together."""
        settings = self._require_supported(reviewed, provider)
        return self._encode(text, settings.query_prefix, reviewed.effective.context_tokens)

    @classmethod
    def _require_supported(
        cls, reviewed: ReviewedModelSettingsDTO, provider: ModelConnectionProvider
    ) -> EmbeddingModelSettingsDTO:
        settings = reviewed.effective.settings
        if (
            provider is not ModelConnectionProvider.OPENAI
            or reviewed.selection.model != "text-embedding-3-small"
            or reviewed.selection.role is not ModelRole.EMBEDDING
            or not isinstance(settings, EmbeddingModelSettingsDTO)
            or settings.expected_provider != ModelConnectionProvider.OPENAI.value
            or reviewed.effective.token_bound != cls.token_bound
        ):
            raise InvalidInputError("The selection has unsupported OpenAI embedding settings.")
        return settings

    def _encode(self, text: str, prefix: str, context_tokens: int) -> tuple[int, ...]:
        if type(text) is not str or type(prefix) is not str:
            raise InvalidInputError("The embedding input must be valid UTF-8 text.")
        limit = min(context_tokens, _MODEL_MAX_TOKENS)
        # No ordinary token can cover more bytes than the longest verified rank.
        max_bytes = limit * self._max_token_bytes
        if len(text) + len(prefix) > max_bytes:
            raise InvalidInputError("The embedding input exceeds the token limit.")
        prepared = prefix + text
        try:
            byte_count = len(prepared.encode("utf-8"))
        except UnicodeEncodeError:
            raise InvalidInputError("The embedding input must be valid UTF-8 text.") from None
        if byte_count > max_bytes:
            raise InvalidInputError("The embedding input exceeds the token limit.")

        tokens = self._encoding.encode_ordinary(prepared)
        if len(tokens) > limit:
            raise InvalidInputError("The embedding input exceeds the token limit.")
        if not tokens:
            raise InvalidInputError("The embedding input must contain at least one token.")
        return tuple(tokens)

    @staticmethod
    def _open_asset(path: str, flags: int) -> int:
        return os.open(path, flags | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_NOCTTY)

    @classmethod
    def _read_ranks(cls, asset_path: Path) -> dict[bytes, int]:
        with open(asset_path, "rb", opener=cls._open_asset) as asset:
            facts = os.fstat(asset.fileno())
            if not stat.S_ISREG(facts.st_mode) or facts.st_size != _CL100K_BYTES:
                raise ValueError("Invalid rank asset.")
            data = asset.read(_CL100K_BYTES + 1)
        if len(data) != _CL100K_BYTES or sha256(data).hexdigest() != _CL100K_SHA256:
            raise ValueError("Invalid rank asset.")

        ranks: dict[bytes, int] = {}
        for rank, line in enumerate(data.splitlines()):
            encoded, _, raw_rank = line.partition(b" ")
            token = b64decode(encoded, validate=True)
            if (
                raw_rank != str(rank).encode("ascii")
                or not token
                or b64encode(token) != encoded
                or token in ranks
            ):
                raise ValueError("Invalid rank asset.")
            ranks[token] = rank
        if len(ranks) != _CL100K_RANKS or any(bytes((byte,)) not in ranks for byte in range(256)):
            raise ValueError("Invalid rank asset.")
        return ranks
