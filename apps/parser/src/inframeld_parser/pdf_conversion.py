"""Run one pinned local PDF conversion inside the private parser process."""

import json
import os
import re
import stat
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from hashlib import file_digest, sha256
from importlib.metadata import PackageNotFoundError, version
from io import BufferedReader, BytesIO
from pathlib import Path
from typing import TypedDict, cast

from inframeld_parser.canonical_pdf import (
    CanonicalPdf,
    InvalidCanonicalPdf,
    TableBlock,
    TableCell,
    TextBlock,
    canonicalize,
)

MAX_INPUT_BYTES = 25 * 1024**2
_MAX_PAGES = 500
_MANIFEST_SHA256 = "7ea9f3c967a7bc66d2501e466334e7aef46a639e01a11376888321e0f0a51d0e"
_PDF_HEADER = re.compile(rb"%PDF-(?:1\.[0-7]|2\.0)[\r\n]")


class _AssetFile(TypedDict):
    path: str
    bytes: int
    sha256: str


class _Asset(TypedDict):
    directory: str
    files: list[_AssetFile]


class _AssetManifest(TypedDict):
    assets: list[_Asset]
    licenseFiles: list[_AssetFile]


class PdfConversionError(ValueError):
    """The selected input or local converter could not produce complete data."""


def convert_pdf(source: Path, *, asset_root: Path, manifest: Path) -> CanonicalPdf:
    """Convert a local file in caller-owned scratch using prepared read-only assets.

    The caller owns OS isolation, input path ancestry, and process lifetime.
    Later validation must bind these bytes to the admitted source and attempt.
    """
    try:
        with _open_regular_file(source) as file:
            content = file.read(MAX_INPUT_BYTES + 1)
    except OSError:
        raise PdfConversionError("The source must be a regular local file.") from None
    if len(content) > MAX_INPUT_BYTES:
        raise PdfConversionError("The PDF exceeds the input size limit.")
    if not _PDF_HEADER.match(content):
        raise PdfConversionError("The source has no supported PDF header.")

    _verify_assets(asset_root, manifest)
    try:
        return canonicalize(
            _docling_blocks(content, asset_root), source_sha256=sha256(content).hexdigest()
        )
    except InvalidCanonicalPdf as error:
        raise PdfConversionError(str(error)) from None


@contextmanager
def _open_regular_file(path: Path) -> Generator[BufferedReader]:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise OSError("Expected a regular file.")
        with open(descriptor, "rb", closefd=False) as file:
            yield file
    finally:
        os.close(descriptor)


def _verify_assets(root: Path, manifest: Path) -> None:
    try:
        with _open_regular_file(manifest) as file:
            content = file.read(32 * 1024)
    except OSError:
        raise PdfConversionError("The pinned parser manifest is unavailable.") from None
    if sha256(content).hexdigest() != _MANIFEST_SHA256:
        raise PdfConversionError("The parser manifest identity does not match.")
    # The digest fixes the complete manifest and its shape before loading any asset.
    selected = cast("_AssetManifest", json.loads(content))
    members = {Path(file["path"]): file for file in selected["licenseFiles"]}
    for asset in selected["assets"]:
        for file in asset["files"]:
            members[Path(asset["directory"], file["path"])] = file
    directories = {parent for path in members for parent in path.parents if parent != Path(".")}
    seen: set[Path] = set()
    try:
        if root.is_symlink() or not root.is_dir():
            raise PdfConversionError("The parser asset inventory is unavailable.")
        for path in root.rglob("*"):
            relative = path.relative_to(root)
            mode = path.lstat().st_mode
            if stat.S_ISDIR(mode) and relative in directories:
                continue
            if not stat.S_ISREG(mode) or relative not in members:
                raise PdfConversionError("The parser asset inventory does not match.")
            seen.add(relative)
        if seen != members.keys():
            raise PdfConversionError("The parser asset inventory does not match.")
        for path, expected in members.items():
            with _open_regular_file(root / path) as file:
                if (
                    os.fstat(file.fileno()).st_size != expected["bytes"]
                    or file_digest(file, "sha256").hexdigest() != expected["sha256"]
                ):
                    raise PdfConversionError("A pinned parser asset does not match.")
    except OSError:
        raise PdfConversionError("The parser asset inventory is unavailable.") from None


def _docling_blocks(content: bytes, asset_root: Path) -> Iterator[TextBlock | TableBlock]:
    try:
        if (version("docling-slim"), version("docling-core")) != ("2.148.0", "2.106.0"):
            raise PdfConversionError("The pinned Docling versions are required.")
        from huggingface_hub.constants import HF_HUB_OFFLINE
    except (ImportError, PackageNotFoundError):
        raise PdfConversionError("The pinned Docling runtime is unavailable.") from None
    if not HF_HUB_OFFLINE:
        raise PdfConversionError("The Docling runtime must be started offline.")

    from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
    from docling.datamodel.base_models import ConversionStatus, DocumentStream, InputFormat
    from docling.datamodel.object_detection_engine_options import (
        TransformersObjectDetectionEngineOptions,
    )
    from docling.datamodel.pipeline_options import (
        LayoutObjectDetectionOptions,
        PdfPipelineOptions,
        TableFormerMode,
        TableStructureOptions,
    )
    from docling.datamodel.stage_model_specs import ObjectDetectionModelSpec
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.exceptions import ConversionError
    from docling_core.types.doc import FormulaItem, RichTableCell, TableItem, TextItem

    options = PdfPipelineOptions(
        artifacts_path=asset_root,
        accelerator_options=AcceleratorOptions(device=AcceleratorDevice.CPU, num_threads=2),
        enable_remote_services=False,
        allow_external_plugins=False,
        do_ocr=False,
        do_picture_classification=False,
        do_picture_description=False,
        do_code_enrichment=False,
        do_formula_enrichment=False,
        do_table_structure=True,
        layout_options=LayoutObjectDetectionOptions(
            model_spec=ObjectDetectionModelSpec(
                name="Heron",
                repo_id="docling-project/docling-layout-heron",
                revision="8f39ad3c0b4c58e9c2d2c84a38465abf757272d8",
            ),
            engine_options=TransformersObjectDetectionEngineOptions(compile_model=False),
        ),
        table_structure_options=TableStructureOptions(
            mode=TableFormerMode.ACCURATE, do_cell_matching=True
        ),
    )
    converter = DocumentConverter(
        allowed_formats=[InputFormat.PDF],
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)},
    )
    with BytesIO(content) as stream:
        try:
            result = converter.convert(
                DocumentStream(name="source.pdf", stream=stream),
                max_file_size=MAX_INPUT_BYTES,
                max_num_pages=_MAX_PAGES,
            )
        except ConversionError:
            raise PdfConversionError("Docling could not complete the PDF conversion.") from None
    pages = result.input.page_count
    if result.status is not ConversionStatus.SUCCESS or not (1 <= pages <= _MAX_PAGES):
        raise PdfConversionError("Docling could not complete the PDF conversion.")

    for item, _ in result.document.iterate_items(traverse_pictures=True):
        if not isinstance(item, (TextItem, TableItem)):
            continue
        locations = tuple(sorted({entry.page_no for entry in item.prov}))
        if any(page > pages for page in locations):
            raise PdfConversionError("Docling returned an invalid source page.")
        if isinstance(item, FormulaItem) and not item.text and item.orig:
            raise PdfConversionError("A native PDF formula has no supported text representation.")
        if isinstance(item, TextItem):
            yield TextBlock(item.text, locations)
            continue
        cells: list[TableCell] = []
        for cell in item.data.table_cells:
            if isinstance(cell, RichTableCell):
                raise PdfConversionError("Rich table cells are unavailable for native PDF.")
            cells.append(
                TableCell(
                    cell.start_row_offset_idx,
                    cell.start_col_offset_idx,
                    cell.end_row_offset_idx,
                    cell.end_col_offset_idx,
                    cell.text,
                    cell.column_header,
                    cell.row_header,
                )
            )
        yield TableBlock(item.data.num_rows, item.data.num_cols, tuple(cells), locations)
