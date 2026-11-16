"""Serialize one PDF's reading order and exact source coordinates."""

import json
from collections.abc import Iterable
from dataclasses import dataclass
from hashlib import sha256

MAX_TEXT_BYTES = 10 * 1024**2
MAX_OUTPUT_BYTES = 32 * 1024**2


class InvalidCanonicalPdf(ValueError):
    """The conversion cannot produce complete bounded canonical PDF data."""


@dataclass(frozen=True, slots=True)
class TextBlock:
    text: str
    pages: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class TableCell:
    row: int
    column: int
    end_row: int
    end_column: int
    text: str
    column_header: bool = False
    row_header: bool = False


@dataclass(frozen=True, slots=True)
class TableBlock:
    rows: int
    columns: int
    cells: tuple[TableCell, ...]
    pages: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class CanonicalPdf:
    """Carry frozen conversion bytes, ready for the separate attempt binding."""

    source_sha256: str
    canonical_bytes: bytes

    @property
    def canonical_sha256(self) -> str:
        return sha256(self.canonical_bytes).hexdigest()


def canonicalize(blocks: Iterable[TextBlock | TableBlock], *, source_sha256: str) -> CanonicalPdf:
    """Freeze reading-order blocks and cell mappings in Unicode code points."""
    if len(source_sha256) != 64 or any(char not in "0123456789abcdef" for char in source_sha256):
        raise InvalidCanonicalPdf("The source digest is invalid.")

    writer = _CanonicalWriter()
    for index, block in enumerate(blocks):
        if index:
            writer.write_text("\n")
            writer.write_structure(b",")
        if not block.pages or any(page < 1 for page in block.pages):
            raise InvalidCanonicalPdf("The block has no valid source page.")
        if isinstance(block, TextBlock):
            span = writer.write_text(block.text)
            writer.write_structure(_json({"kind": "text", "pages": block.pages, "span": span}))
        else:
            writer.write_table(block)
    return CanonicalPdf(source_sha256, writer.finish())


def _json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


class _CanonicalWriter:
    def __init__(self) -> None:
        self._text = bytearray()
        self._structure = bytearray(b'{"format":"inframeld-pdf-canonical-v1","blocks":[')
        self._position = 0
        self._has_text = False

    def write_text(self, value: str) -> tuple[int, int]:
        normalized = value.replace("\r\n", "\n").replace("\r", "\n")
        try:
            encoded = normalized.encode("utf-8")
        except UnicodeEncodeError:
            raise InvalidCanonicalPdf("The extracted text is not valid Unicode.") from None
        if len(self._text) + len(encoded) > MAX_TEXT_BYTES:
            raise InvalidCanonicalPdf("Canonical PDF text limit exceeded.")
        self._text.extend(encoded)
        start = self._position
        self._position += len(normalized)
        if not self._has_text:
            self._has_text = bool(normalized.strip())
        return start, self._position

    def write_structure(self, *parts: bytes) -> None:
        if len(self._structure) + sum(map(len, parts)) > MAX_OUTPUT_BYTES:
            raise InvalidCanonicalPdf("Canonical PDF structured output limit exceeded.")
        for part in parts:
            self._structure.extend(part)

    def write_table(self, block: TableBlock) -> None:
        rows, columns = block.rows, block.columns
        if rows < 1 or columns < 1:
            raise InvalidCanonicalPdf("The table dimensions are invalid.")
        slots = rows * columns
        if slots - 1 + len(self._text) > MAX_TEXT_BYTES:
            raise InvalidCanonicalPdf("Canonical PDF text limit exceeded.")
        cells = sorted(block.cells, key=lambda cell: (cell.row, cell.column))
        _check_cell_coverage(cells, rows, columns)
        self.write_structure(
            b'{"kind":"table","pages":',
            _json(block.pages),
            b',"rows":',
            _json(rows),
            b',"columns":',
            _json(columns),
            b',"cells":[',
        )
        index = 0
        for row in range(rows):
            if row:
                self.write_text("\n")
            column = 0
            while index < len(cells) and cells[index].row == row:
                cell = cells[index]
                self.write_text("\t" * (cell.column - column))
                if index:
                    self.write_structure(b",")
                self.write_structure(
                    _json(
                        {
                            "row": (cell.row, cell.end_row),
                            "column": (cell.column, cell.end_column),
                            "span": self.write_text(cell.text),
                            "columnHeader": cell.column_header,
                            "rowHeader": cell.row_header,
                        }
                    )
                )
                column = cell.column
                index += 1
            self.write_text("\t" * (columns - 1 - column))
        self.write_structure(b"]}")

    def finish(self) -> bytes:
        if not self._has_text:
            raise InvalidCanonicalPdf("The PDF contains no usable extracted text.")
        self.write_structure(b'],"text":', _json(self._text.decode("utf-8")), b"}")
        return bytes(self._structure)


def _check_cell_coverage(cells: list[TableCell], rows: int, columns: int) -> None:
    # One byte per bounded slot checks merged rectangles without expanding their text.
    covered = bytearray(rows * columns)
    for cell in cells:
        if not (
            0 <= cell.row < cell.end_row <= rows and 0 <= cell.column < cell.end_column <= columns
        ):
            raise InvalidCanonicalPdf("A table cell is outside its table.")
        fill = b"\x01" * (cell.end_column - cell.column)
        for row in range(cell.row, cell.end_row):
            occupied = slice(row * columns + cell.column, row * columns + cell.end_column)
            if any(covered[occupied]):
                raise InvalidCanonicalPdf("The table contains overlapping cells.")
            covered[occupied] = fill
