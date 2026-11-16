"""Exercise the private PDF boundary with controlled and real local inputs."""

import json
import os
import unittest
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, TypedDict, cast
from unittest.mock import patch

from inframeld_parser.canonical_pdf import CanonicalPdf, TextBlock
from inframeld_parser.pdf_conversion import PdfConversionError, convert_pdf

if TYPE_CHECKING:
    from docling_core.types.doc import DoclingDocument, ProvenanceItem

_ROOT = Path(__file__).resolve().parents[3]
_MANIFEST = _ROOT / "config/models/docling-parser-v1.json"
_ALICE = _ROOT / "apps/backend/tests/fixtures/documents/alice-in-wonderland.pdf"
_PDF = b"%PDF-1.7\n"


class LocalPdfInputTest(unittest.TestCase):
    def test_rejects_symlink_directory_and_fifo_before_parser_loading(self) -> None:
        with TemporaryDirectory() as scratch:
            root = Path(scratch)
            pdf = root / "input.pdf"
            pdf.write_bytes(_PDF)
            link = root / "link.pdf"
            link.symlink_to(pdf)
            fifo = root / "fifo.pdf"
            os.mkfifo(fifo)
            for source in (link, root, fifo):
                with (
                    self.subTest(source=source.name),
                    self.assertRaisesRegex(PdfConversionError, "regular local file"),
                ):
                    convert_pdf(source, asset_root=root, manifest=_MANIFEST)

    def test_rejects_oversize_and_non_pdf_sources_before_parser_loading(self) -> None:
        with TemporaryDirectory() as scratch:
            root = Path(scratch)
            source = root / "source"
            source.write_bytes(_PDF)
            with (
                patch("inframeld_parser.pdf_conversion.MAX_INPUT_BYTES", 8),
                self.assertRaisesRegex(PdfConversionError, "size limit"),
            ):
                convert_pdf(source, asset_root=root, manifest=_MANIFEST)
            source.write_bytes(b"ordinary text")
            with self.assertRaisesRegex(PdfConversionError, "PDF header"):
                convert_pdf(source, asset_root=root, manifest=_MANIFEST)

    def test_refuses_an_untrusted_manifest_or_missing_asset_without_loading_models(self) -> None:
        with TemporaryDirectory() as scratch:
            root = Path(scratch)
            source = root / "input.pdf"
            source.write_bytes(_PDF)
            manifest = root / "manifest.json"
            manifest.write_bytes(_MANIFEST.read_bytes() + b" ")
            with self.assertRaisesRegex(PdfConversionError, "manifest identity"):
                convert_pdf(source, asset_root=root, manifest=manifest)
            assets = root / "assets"
            assets.mkdir()
            with self.assertRaisesRegex(PdfConversionError, "asset inventory"):
                convert_pdf(source, asset_root=assets, manifest=_MANIFEST)

    def test_consumes_the_validated_input_snapshot_and_refuses_same_size_asset_changes(
        self,
    ) -> None:
        with TemporaryDirectory() as scratch:
            root = Path(scratch)
            source = root / "input"
            source.write_bytes(_PDF)
            assets = root / "assets"
            assets.mkdir()
            asset = assets / "model"
            asset.write_bytes(b"fixed")
            manifest = root / "manifest.json"
            manifest_data = json.dumps(
                {
                    "assets": [],
                    "licenseFiles": [
                        {"path": "model", "bytes": 5, "sha256": sha256(b"fixed").hexdigest()}
                    ],
                }
            ).encode()
            manifest.write_bytes(manifest_data)
            with (
                patch(
                    "inframeld_parser.pdf_conversion._MANIFEST_SHA256",
                    sha256(manifest_data).hexdigest(),
                ),
                patch(
                    "inframeld_parser.pdf_conversion._docling_blocks",
                    return_value=iter([TextBlock("Converted text", (1,))]),
                ) as extract,
            ):
                artifact = convert_pdf(source, asset_root=assets, manifest=manifest)
                extract.assert_called_once_with(_PDF, assets)
                self.assertEqual(artifact.source_sha256, sha256(_PDF).hexdigest())
                asset.write_bytes(b"alter")
                with self.assertRaisesRegex(PdfConversionError, "pinned parser asset"):
                    convert_pdf(source, asset_root=assets, manifest=manifest)
                extract.assert_called_once()


class _CellView(TypedDict):
    row: list[int]
    column: list[int]
    span: list[int]


class _BlockView(TypedDict):
    kind: str
    pages: list[int]
    span: list[int]
    cells: list[_CellView]


class _ConversionView(TypedDict):
    text: str
    blocks: list[_BlockView]


@unittest.skipUnless(os.getenv("INFRAMELD_PARSER_TEST_ASSETS"), "Requires pinned offline assets")
class TrustedPdfConversionTest(unittest.TestCase):
    def test_maps_native_picture_caption_and_child_text_once(self) -> None:
        from docling_core.types.doc import DocItemLabel, DoclingDocument

        document = DoclingDocument(name="Picture text")
        document.add_text(DocItemLabel.PARAGRAPH, "Body text", prov=_first_page(9))
        picture = document.add_picture(prov=_first_page(0))
        caption = document.add_text(
            DocItemLabel.CAPTION, "Chart caption", prov=_first_page(13), parent=picture
        )
        picture.captions.append(caption.get_ref())
        document.add_text(DocItemLabel.TEXT, "North axis", prov=_first_page(10), parent=picture)

        artifact = self._convert_document(document)
        view = cast("_ConversionView", json.loads(artifact.canonical_bytes))
        self.assertEqual(view["text"], "Body text\nChart caption\nNorth axis")
        self.assertEqual(
            view["blocks"],
            [
                {"kind": "text", "pages": [1], "span": [0, 9]},
                {"kind": "text", "pages": [1], "span": [10, 23]},
                {"kind": "text", "pages": [1], "span": [24, 34]},
            ],
        )

    def test_rejects_an_orig_only_formula_even_with_mappable_body_text(self) -> None:
        from docling_core.types.doc import DocItemLabel, DoclingDocument

        document = DoclingDocument(name="Unsupported formula")
        document.add_text(DocItemLabel.PARAGRAPH, "Body text", prov=_first_page(9))
        document.add_formula(text="", orig="x = 1", prov=_first_page(5))

        with self.assertRaisesRegex(PdfConversionError, "formula"):
            self._convert_document(document)

    def _convert_document(self, document: "DoclingDocument") -> CanonicalPdf:
        """Supply a pinned native result without classifying an artificial PDF."""
        from docling.datamodel.base_models import ConversionStatus
        from docling.datamodel.document import ConversionResult, InputDocument
        from docling.document_converter import DocumentConverter

        result = ConversionResult(
            input=InputDocument.model_construct(page_count=1),
            status=ConversionStatus.SUCCESS,
            document=document,
        )
        assets = Path(os.environ["INFRAMELD_PARSER_TEST_ASSETS"])
        with patch.object(DocumentConverter, "convert", return_value=result):
            return convert_pdf(_ALICE, asset_root=assets, manifest=_MANIFEST)

    def test_alice_text_maps_to_the_one_source_page(self) -> None:
        assets = Path(os.environ["INFRAMELD_PARSER_TEST_ASSETS"])
        artifact = convert_pdf(_ALICE, asset_root=assets, manifest=_MANIFEST)
        self.assertEqual(artifact.source_sha256, sha256(_ALICE.read_bytes()).hexdigest())
        document = cast("_ConversionView", json.loads(artifact.canonical_bytes))
        self.assertTrue(all(block["pages"] == [1] for block in document["blocks"]))
        self.assertTrue(
            any(
                "Oh dear! Oh dear! I shall be late!"
                in document["text"][block["span"][0] : block["span"][1]]
                for block in document["blocks"]
                if block["kind"] == "text"
            )
        )

    @unittest.skipUnless(os.getenv("INFRAMELD_PARSER_TEST_TABLE"), "Requires the ruled-table PDF")
    def test_reads_the_original_ruled_table_cells_by_their_own_spans(self) -> None:
        assets = Path(os.environ["INFRAMELD_PARSER_TEST_ASSETS"])
        table = Path(os.environ["INFRAMELD_PARSER_TEST_TABLE"])
        artifact = convert_pdf(table, asset_root=assets, manifest=_MANIFEST)
        self.assertEqual(artifact.source_sha256, sha256(table.read_bytes()).hexdigest())
        document = cast("_ConversionView", json.loads(artifact.canonical_bytes))
        self.assertIn("Quarterly asset inventory for the workshop.", document["text"])
        tables = [block for block in document["blocks"] if block["kind"] == "table"]
        self.assertEqual(len(tables), 1)
        self.assertEqual(tables[0]["pages"], [1])
        self.assertEqual(
            {
                (cell["row"][0], cell["column"][0]): document["text"][
                    cell["span"][0] : cell["span"][1]
                ].strip()
                for cell in tables[0]["cells"]
            },
            {
                (0, 0): "Item",
                (0, 1): "Count",
                (1, 0): "Amber valve",
                (1, 1): "17",
                (2, 0): "Cobalt gauge",
                (2, 1): "29",
            },
        )


def _first_page(characters: int) -> "ProvenanceItem":
    from docling_core.types.doc import BoundingBox, CoordOrigin, ProvenanceItem

    return ProvenanceItem(
        page_no=1,
        bbox=BoundingBox(l=1, t=2, r=3, b=1, coord_origin=CoordOrigin.BOTTOMLEFT),
        charspan=(0, characters),
    )
