"""Bind stock Docling prose chunks to their exact canonical source text."""

import json
import warnings
from collections.abc import Callable, Generator, Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from heapq import merge
from importlib.metadata import PackageNotFoundError, version
from itertools import islice
from typing import TYPE_CHECKING, TypedDict, cast, override

if TYPE_CHECKING:
    from pathlib import Path

    from docling_core.types.doc import DocItem, DoclingDocument
    from inframeld_parser.canonical_pdf import CanonicalPdf
    from semchunk.semchunk import Chunker
    from transformers import PreTrainedTokenizerBase

_MAX_CHUNKS = 2000
_MAX_EMITTED_TOKENS = 1_000_000
_SPLIT_WHITESPACE = " \t\n"


class _TextView(TypedDict):
    kind: str
    span: tuple[int, int]


class _CanonicalProse(TypedDict):
    text: str
    blocks: list[_TextView]


@dataclass(frozen=True, slots=True)
class ProseChunk:
    text: str
    start: int
    end: int


class ProseMappingError(ValueError):
    """The stock chunk output lacks an exact supported source mapping."""


@dataclass(frozen=True, slots=True)
class _Split:
    source: str
    budget: int
    pieces: tuple[str, ...]


def map_stock_prose(
    document: "DoclingDocument",
    items: list["DocItem"],
    artifact: "CanonicalPdf",
    asset_root: "Path",
    max_content_tokens: int,
) -> tuple[ProseChunk, ...]:
    """Verify unchanged stock output against the same document's prose spans."""
    try:
        if version("semchunk") != "3.2.5":
            raise ProseMappingError("The pinned Semchunk version is required.")
        from docling_core.transforms.chunker.doc_chunk import DocChunk
        from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
        from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
        from docling_core.transforms.serializer.base import BaseDocSerializer
        from docling_core.types.doc import TextItem
        from semchunk import chunkerify
        from tokenizers import Tokenizer
        from transformers.tokenization_utils_tokenizers import TokenizersBackend
    except (ImportError, PackageNotFoundError):
        raise ProseMappingError("The pinned stock chunking runtime is unavailable.") from None

    canonical = cast("_CanonicalProse", json.loads(artifact.canonical_bytes))
    source = canonical["text"]
    if len(items) != len(canonical["blocks"]):
        raise ProseMappingError("Canonical prose source items could not be verified.")
    anchors: dict[str, tuple[DocItem, int, int]] = {}
    for item, block in zip(items, canonical["blocks"], strict=True):
        if not isinstance(item, TextItem) or block["kind"] != "text":
            raise ProseMappingError("Verified stock chunk mapping supports plain prose only.")
        start, end = block["span"]
        literal = item.text.replace("\r\n", "\n").replace("\r", "\n")
        if (
            item.self_ref in anchors
            or item.get_ref().resolve(document) is not item
            or not 0 <= start <= end <= len(source)
            or literal != source[start:end]
        ):
            raise ProseMappingError("Canonical prose source items could not be verified.")
        anchors[item.self_ref] = item, start, end

    backend = Tokenizer.from_file(
        str(asset_root / "sentence-transformers--all-MiniLM-L6-v2" / "tokenizer.json")
    )
    backend.no_padding()
    backend.no_truncation()
    tokenizer = HuggingFaceTokenizer(
        tokenizer=TokenizersBackend(
            tokenizer_object=backend,
            model_max_length=1024,
            cls_token="[CLS]",
            sep_token="[SEP]",
            pad_token="[PAD]",
            unk_token="[UNK]",
            mask_token="[MASK]",
        ),
        max_tokens=max_content_tokens,
    )
    splits: dict[str, _Split] = {}

    class ObservedHybridChunker(HybridChunker):
        @override
        def segment(
            self, doc_chunk: DocChunk, available_length: int, doc_serializer: BaseDocSerializer
        ) -> list[str]:
            pieces = super().segment(doc_chunk, available_length, doc_serializer)
            if len(pieces) > _MAX_CHUNKS:
                raise ProseMappingError("The stock prose chunk count exceeded its limit.")
            if len(doc_chunk.meta.doc_items) == 1:
                ref = doc_chunk.meta.doc_items[0].self_ref
                splits[ref] = _Split(doc_chunk.text, available_length, tuple(pieces))
            return pieces

    chunker = ObservedHybridChunker(
        tokenizer=tokenizer, merge_peers=False, repeat_table_header=True
    )
    with reject_raw_context_warning():
        emitted = list(islice(chunker.chunk(dl_doc=document), _MAX_CHUNKS + 1))
    if not 1 <= len(emitted) <= _MAX_CHUNKS:
        raise ProseMappingError("The stock prose chunk count exceeded its limit or was empty.")

    groups: dict[str, list[str]] = {}
    previous_ref = None
    total_tokens = 0
    for chunk in emitted:
        if not isinstance(chunk, DocChunk) or len(chunk.meta.doc_items) != 1:
            raise ProseMappingError("Stock prose chunks must refer to one canonical text item.")
        ref_item = chunk.meta.doc_items[0]
        ref = ref_item.self_ref
        anchor = anchors.get(ref)
        if anchor is None or ref_item.get_ref().resolve(document) is not anchor[0]:
            raise ProseMappingError("Stock prose chunk source references could not be verified.")
        if ref in groups and ref != previous_ref:
            raise ProseMappingError("Stock prose chunks are out of source order.")
        if chunker.contextualize(chunk) != chunk.text:
            raise ProseMappingError("Stock prose chunk context could not be verified.")
        count = tokenizer.count_tokens(chunk.text)
        total_tokens += count
        if not 1 <= count <= max_content_tokens or total_tokens > _MAX_EMITTED_TOKENS:
            raise ProseMappingError("The stock prose token limit was exceeded or empty.")
        groups.setdefault(ref, []).append(chunk.text)
        previous_ref = ref

    # These anchors came from the canonical walk with picture traversal enabled.
    # The same walk without picture traversal still includes the picture's captions.
    without_picture_traversal = {
        item.self_ref for item, _ in document.iterate_items(traverse_pictures=False)
    }
    omitted_picture_children = (
        (start, end)
        for ref, (_, start, end) in anchors.items()
        if ref not in without_picture_traversal and ref not in groups
    )
    require_prose_coverage(
        source, (anchors[ref][1:] for ref in groups), picture_children=omitted_picture_children
    )

    verified: list[ProseChunk] = []
    # Semchunk accepts the stock fast tokenizer through its encode and get_vocab methods.
    chunker_for_offsets = cast("Callable[[PreTrainedTokenizerBase, int], Chunker]", chunkerify)
    for ref, texts in groups.items():
        _, start, end = anchors[ref]
        original = source[start:end]
        pieces = tuple(texts)
        if pieces == (original,):
            offsets = ((0, len(original)),)
        else:
            split = splits.get(ref)
            if (
                split is None
                or split.source != original
                or split.pieces != pieces
                or not 1 <= split.budget <= max_content_tokens
            ):
                raise ProseMappingError("Stock prose split evidence could not be verified.")
            replay = chunker_for_offsets(tokenizer.get_tokenizer(), split.budget)
            replayed = replay(original, offsets=True)
            if not isinstance(replayed, tuple) or replayed[0] != texts:
                raise ProseMappingError("Stock prose split evidence could not be verified.")
            offsets = tuple(cast("list[tuple[int, int]]", replayed[1]))
        verified.extend(verify_prose_spans(original, pieces, offsets, origin_start=start))
    return tuple(verified)


def require_prose_coverage(
    source: str,
    emitted_items: Iterable[tuple[int, int]],
    *,
    picture_children: Iterable[tuple[int, int]],
) -> None:
    """Require ordered coverage, allowing only complete picture-child spans and whitespace."""
    cursor = 0
    for start, end in merge(emitted_items, picture_children):
        if not cursor <= start <= end <= len(source) or source[cursor:start].strip(
            _SPLIT_WHITESPACE
        ):
            raise ProseMappingError("Stock prose chunk source coverage could not be verified.")
        cursor = end
    if source[cursor:].strip(_SPLIT_WHITESPACE):
        raise ProseMappingError("Stock prose chunk source coverage could not be verified.")


@contextmanager
def reject_raw_context_warning() -> Generator[None]:
    """Stop the pinned stock warning before it exposes source text and drops context."""
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "error",
            message=(
                r"^Headers and captions for this chunk are longer than the total "
                r"available size for the chunk, so they will be ignored:"
            ),
            category=UserWarning,
            module=r"^docling_core\.transforms\.chunker\.hybrid_chunker$",
        )
        try:
            yield
        except UserWarning:
            raise ProseMappingError("Stock prose chunk context could not be verified.") from None


def verify_prose_spans(
    source: str,
    pieces: tuple[str, ...],
    offsets: tuple[tuple[int, int], ...],
    *,
    origin_start: int,
) -> tuple[ProseChunk, ...]:
    """Map exact ordered slices and leave verified split whitespace uncovered."""
    if not pieces or len(pieces) != len(offsets):
        raise ProseMappingError("Stock prose split evidence could not be verified.")
    verified: list[ProseChunk] = []
    cursor = 0
    for piece, (start, end) in zip(pieces, offsets, strict=True):
        if (
            type(start) is not int
            or type(end) is not int
            or not cursor <= start < end <= len(source)
            or source[cursor:start].strip(_SPLIT_WHITESPACE)
            or source[start:end] != piece
        ):
            raise ProseMappingError("Stock prose offsets did not match the canonical source.")
        verified.append(ProseChunk(piece, origin_start + start, origin_start + end))
        cursor = end
    if source[cursor:].strip(_SPLIT_WHITESPACE):
        raise ProseMappingError("Stock prose offsets did not cover the canonical source.")
    return tuple(verified)
