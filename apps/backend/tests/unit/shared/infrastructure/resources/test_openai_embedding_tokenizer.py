import hashlib
import os
from base64 import b64encode
from dataclasses import replace
from pathlib import Path
from typing import Literal
from uuid import UUID

import pytest

from inframeld_backend.access.domain.enums.model_connection_provider import ModelConnectionProvider
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.effective_model_settings_dto import (
    EffectiveModelSettingsDTO,
)
from inframeld_backend.shared.application.dtos.embedding_model_settings_dto import (
    EmbeddingModelSettingsDTO,
)
from inframeld_backend.shared.application.dtos.model_selection_dto import ModelSelectionDTO
from inframeld_backend.shared.application.dtos.reviewed_model_settings_dto import (
    ReviewedModelSettingsDTO,
)
from inframeld_backend.shared.application.enums.embedding_distance import EmbeddingDistance
from inframeld_backend.shared.application.enums.embedding_normalization import (
    EmbeddingNormalization,
)
from inframeld_backend.shared.application.enums.model_role import ModelRole
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
    InvalidInputError,
)
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId
from inframeld_backend.shared.infrastructure.resources import openai_embedding_tokenizer
from inframeld_backend.shared.infrastructure.resources.openai_embedding_tokenizer import (
    OpenAIEmbeddingTokenizer,
)


@pytest.fixture
def local_ranks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    tokens = [bytes((rank,)) for rank in range(256)] + [b"ab"]
    data = b"".join(
        b64encode(token) + f" {rank}\n".encode("ascii") for rank, token in enumerate(tokens)
    )
    path = tmp_path / "local-ranks.tiktoken"
    path.write_bytes(data)
    monkeypatch.setattr(openai_embedding_tokenizer, "_CL100K_BYTES", len(data))
    monkeypatch.setattr(openai_embedding_tokenizer, "_CL100K_RANKS", len(tokens))
    monkeypatch.setattr(
        openai_embedding_tokenizer, "_CL100K_SHA256", hashlib.sha256(data).hexdigest()
    )
    return path


def _reviewed(
    *,
    document_prefix: str = "",
    query_prefix: str = "",
    context_tokens: int = 8_191,
) -> ReviewedModelSettingsDTO:
    return ReviewedModelSettingsDTO(
        selection=ModelSelectionDTO(
            ProjectId(UUID(int=1)),
            ModelConnectionId(UUID(int=2)),
            "text-embedding-3-small",
            ModelRole.EMBEDDING,
        ),
        effective=EffectiveModelSettingsDTO(
            context_tokens,
            OpenAIEmbeddingTokenizer.token_bound,
            EmbeddingModelSettingsDTO(
                1_536,
                EmbeddingNormalization.NONE,
                EmbeddingDistance.COSINE,
                document_prefix,
                query_prefix,
                ModelConnectionProvider.OPENAI.value,
                role=ModelRole.EMBEDDING,
            ),
        ),
        fingerprint="settings",
    )


def test_both_paths_combine_the_saved_prefix_and_text_before_tokenizing(local_ranks: Path) -> None:
    tokenizer = OpenAIEmbeddingTokenizer(local_ranks)
    reviewed = _reviewed(document_prefix="a", query_prefix="c", context_tokens=2)

    assert tokenizer.document_tokens(
        "b", reviewed=reviewed, provider=ModelConnectionProvider.OPENAI
    ) == (256,)
    assert tokenizer.query_tokens(
        "b", reviewed=reviewed, provider=ModelConnectionProvider.OPENAI
    ) == (
        ord("c"),
        ord("b"),
    )


def test_literal_special_token_is_ordinary_text(local_ranks: Path) -> None:
    literal = "<|endoftext|>"
    tokenizer = OpenAIEmbeddingTokenizer(local_ranks)

    assert tokenizer.query_tokens(
        literal, reviewed=_reviewed(), provider=ModelConnectionProvider.OPENAI
    ) == tuple(map(ord, literal))


@pytest.mark.parametrize("mismatch", ["provider", "model", "recipe", "revision"])
def test_rejects_unsupported_model_or_token_recipe(
    local_ranks: Path, mismatch: Literal["provider", "model", "recipe", "revision"]
) -> None:
    tokenizer = OpenAIEmbeddingTokenizer(local_ranks)
    reviewed = _reviewed()
    provider = ModelConnectionProvider.OPENAI
    match mismatch:
        case "provider":
            provider = ModelConnectionProvider.OPENAI_COMPATIBLE
        case "model":
            reviewed = replace(
                reviewed, selection=replace(reviewed.selection, model="private-model")
            )
        case "recipe" | "revision":
            bound = reviewed.effective.token_bound
            changed_bound = (
                replace(bound, implementation="another-encoding")
                if mismatch == "recipe"
                else replace(bound, revision="another-revision")
            )
            reviewed = replace(
                reviewed, effective=replace(reviewed.effective, token_bound=changed_bound)
            )

    with pytest.raises(InvalidInputError, match="unsupported OpenAI embedding settings"):
        tokenizer.document_tokens("ab", reviewed=reviewed, provider=provider)


@pytest.mark.parametrize(("reviewed_limit", "effective_limit"), [(2, 2), (10_000, 8_191)])
def test_uses_the_lower_of_the_reviewed_and_qualified_limits(
    local_ranks: Path, reviewed_limit: int, effective_limit: int
) -> None:
    tokenizer = OpenAIEmbeddingTokenizer(local_ranks)
    reviewed = _reviewed(context_tokens=reviewed_limit)
    provider = ModelConnectionProvider.OPENAI

    assert (
        tokenizer.document_tokens("x" * effective_limit, reviewed=reviewed, provider=provider)
        == (ord("x"),) * effective_limit
    )
    with pytest.raises(InvalidInputError, match="exceeds the token limit"):
        tokenizer.document_tokens("x" * (effective_limit + 1), reviewed=reviewed, provider=provider)


class _UnexpectedEncoding:
    def encode_ordinary(self, text: str) -> list[int]:
        raise AssertionError("Invalid input reached tokenization")


@pytest.mark.parametrize(
    ("prefix", "text", "reason"),
    [
        ("", "abcdef", "exceeds the token limit"),
        ("a", "😀", "exceeds the token limit"),
        ("a", "\ud800", "valid UTF-8"),
        ("\ud800", "a", "valid UTF-8"),
    ],
)
def test_rejects_impossible_lengths_and_invalid_unicode_before_encoding(
    local_ranks: Path,
    monkeypatch: pytest.MonkeyPatch,
    prefix: str,
    text: str,
    reason: str,
) -> None:
    tokenizer = OpenAIEmbeddingTokenizer(local_ranks)
    monkeypatch.setattr(tokenizer, "_encoding", _UnexpectedEncoding(), raising=False)

    with pytest.raises(InvalidInputError, match=reason):
        tokenizer.document_tokens(
            text,
            reviewed=_reviewed(document_prefix=prefix, context_tokens=2),
            provider=ModelConnectionProvider.OPENAI,
        )


@pytest.mark.parametrize("asset_failure", ["missing", "corrupt", "symlink", "fifo", "extra-data"])
def test_unusable_assets_fail_closed_without_revealing_the_path(
    local_ranks: Path, asset_failure: Literal["missing", "corrupt", "symlink", "fifo", "extra-data"]
) -> None:
    match asset_failure:
        case "missing":
            local_ranks.unlink()
        case "corrupt":
            local_ranks.write_bytes(b"!" + local_ranks.read_bytes()[1:])
        case "symlink":
            target = local_ranks.rename(local_ranks.with_name("real-ranks"))
            local_ranks.symlink_to(target)
        case "fifo":
            local_ranks.unlink()
            os.mkfifo(local_ranks)
        case "extra-data":
            local_ranks.write_bytes(local_ranks.read_bytes() + b"X")

    with pytest.raises(DependencyUnavailableError) as exc:
        OpenAIEmbeddingTokenizer(local_ranks)

    assert str(exc.value) == "The pinned OpenAI embedding tokenizer is unavailable."
    assert exc.value.__suppress_context__


def test_pinned_openai_ranks_produce_exact_document_and_query_tokens() -> None:
    path = os.environ.get("INFRAMELD_TEST_OPENAI_CL100K_BASE_PATH")
    if path is None:
        pytest.skip("Set INFRAMELD_TEST_OPENAI_CL100K_BASE_PATH to the pinned local rank file.")
    tokenizer = OpenAIEmbeddingTokenizer(Path(path))
    reviewed = _reviewed(document_prefix="hel", query_prefix=" ", context_tokens=2)
    provider = ModelConnectionProvider.OPENAI

    assert tokenizer.document_tokens("lo world", reviewed=reviewed, provider=provider) == (
        15_339,
        1_917,
    )
    assert tokenizer.query_tokens("hello", reviewed=reviewed, provider=provider) == (24_748,)

    literal_special = tokenizer.query_tokens(
        "<|endoftext|>", reviewed=_reviewed(), provider=provider
    )
    assert literal_special
    assert all(0 <= token < 100_256 for token in literal_special)
