"""Check canonical coordinates independently of the extraction library."""

import json
import unittest
from hashlib import sha256
from unittest.mock import patch

from inframeld_parser.canonical_pdf import (
    InvalidCanonicalPdf,
    TableBlock,
    TableCell,
    TextBlock,
    canonicalize,
)

_SOURCE = sha256(b"pdf source").hexdigest()


class CanonicalPdfTest(unittest.TestCase):
    def test_preserves_unicode_and_whitespace_in_code_point_spans(self) -> None:
        artifact = canonicalize(
            [TextBlock(" A🙂e\u0301\r\nB\r ", (1,)), TextBlock(" C ", (2,))],
            source_sha256=_SOURCE,
        )
        self.assertEqual(artifact.source_sha256, _SOURCE)
        self.assertEqual(
            json.loads(artifact.canonical_bytes),
            {
                "format": "inframeld-pdf-canonical-v1",
                "text": " A🙂e\u0301\nB\n \n C ",
                "blocks": [
                    {"kind": "text", "pages": [1], "span": [0, 9]},
                    {"kind": "text", "pages": [2], "span": [10, 13]},
                ],
            },
        )
        self.assertEqual(artifact.canonical_sha256, sha256(artifact.canonical_bytes).hexdigest())

    def test_preserves_cell_identity_without_repeating_merged_cell_text(self) -> None:
        cells = (
            TableCell(1, 2, 2, 3, ""),
            TableCell(0, 0, 2, 2, "A\tB\r\nC", column_header=True),
            TableCell(0, 2, 1, 3, "🙂"),
        )
        block = TableBlock(2, 3, cells, (2,))
        artifact = canonicalize([block], source_sha256=_SOURCE)
        document = json.loads(artifact.canonical_bytes)
        self.assertEqual(document["text"], "A\tB\nC\t\t🙂\n\t\t")
        self.assertEqual(
            document["blocks"],
            [
                {
                    "kind": "table",
                    "pages": [2],
                    "rows": 2,
                    "columns": 3,
                    "cells": [
                        {
                            "row": [0, 2],
                            "column": [0, 2],
                            "span": [0, 5],
                            "columnHeader": True,
                            "rowHeader": False,
                        },
                        {
                            "row": [0, 1],
                            "column": [2, 3],
                            "span": [7, 8],
                            "columnHeader": False,
                            "rowHeader": False,
                        },
                        {
                            "row": [1, 2],
                            "column": [2, 3],
                            "span": [11, 11],
                            "columnHeader": False,
                            "rowHeader": False,
                        },
                    ],
                }
            ],
        )
        self.assertEqual(
            canonicalize([TableBlock(2, 3, tuple(reversed(cells)), (2,))], source_sha256=_SOURCE),
            artifact,
        )

    def test_rejects_invalid_coordinates_and_overlapping_cells(self) -> None:
        bad_tables = (
            TableBlock(0, 2, (), (1,)),
            TableBlock(1, 2, (TableCell(0, 0, 1, 3, "outside"),), (1,)),
            TableBlock(
                2, 2, (TableCell(0, 0, 2, 2, "first"), TableCell(1, 1, 2, 2, "second")), (1,)
            ),
        )
        for table in bad_tables:
            with self.subTest(table=table), self.assertRaises(InvalidCanonicalPdf):
                canonicalize([table], source_sha256=_SOURCE)

    def test_rejects_empty_invalid_unicode_and_independent_output_limits(self) -> None:
        for blocks in ([], [TextBlock(" ", (1,))], [TextBlock("\ud800", (1,))]):
            with self.subTest(blocks=blocks), self.assertRaises(InvalidCanonicalPdf):
                canonicalize(blocks, source_sha256=_SOURCE)
        with (
            patch("inframeld_parser.canonical_pdf.MAX_TEXT_BYTES", 5),
            self.assertRaisesRegex(InvalidCanonicalPdf, "text limit"),
        ):
            canonicalize([TextBlock("🙂🙂", (1,))], source_sha256=_SOURCE)
        with (
            patch("inframeld_parser.canonical_pdf.MAX_TEXT_BYTES", 5),
            self.assertRaisesRegex(InvalidCanonicalPdf, "text limit"),
        ):
            canonicalize([TableBlock(4, 4, (), (1,))], source_sha256=_SOURCE)
        with (
            patch("inframeld_parser.canonical_pdf.MAX_OUTPUT_BYTES", 150),
            self.assertRaisesRegex(InvalidCanonicalPdf, "structured output limit"),
        ):
            canonicalize(
                [TextBlock("first", (1,)), TextBlock("second", (2,))], source_sha256=_SOURCE
            )
