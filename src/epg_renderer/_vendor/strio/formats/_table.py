"""Strict reading of delimited text tables (internal).

The functions here know nothing about any particular program. They decode text,
validate CSV quoting while keeping physical line numbers, split rows, and offer small
helpers for header names. Format readers such as :mod:`strio.formats.genemapper` build
on them.
"""

from __future__ import annotations

import codecs
import csv
import io
import re
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

from ..errors import DuplicateColumnError, ParseError

DEFAULT_ENCODINGS = ("utf-8-sig", "cp1252", "latin-1")
"""Encodings tried in order when the caller does not name one.

``utf-8-sig`` reads UTF-8 with and without byte-order mark.

``latin-1`` decodes every byte sequence, so the list always yields text; a file in an
unexpected encoding then fails later with a precise header or value error instead.
"""

_UTF16_BOMS = (codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)
_INDEXED_RE = re.compile(r"^(?P<base>.+?)\s+(?P<index>[1-9][0-9]*)$", re.IGNORECASE)
_MAX_INDEX_DIGITS = 6

Row = tuple[int, list[str]]
"""One parsed table row: its first physical source line and its fields."""


def read_text(path: Path, encoding: str | None) -> tuple[str, str]:
    """Return the decoded text of ``path`` and the encoding that decoded it.

    Without an explicit encoding, a UTF-16 byte-order mark selects UTF-16; otherwise
    :data:`DEFAULT_ENCODINGS` are tried in order.
    """

    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ParseError(f"Could not read {path}: {exc.strerror or exc}.") from exc
    if encoding is None and data.startswith(_UTF16_BOMS):
        candidates: tuple[str, ...] = ("utf-16",)
    else:
        candidates = (encoding,) if encoding else DEFAULT_ENCODINGS
    last_error: UnicodeDecodeError | None = None
    for candidate in candidates:
        try:
            return data.decode(candidate), candidate
        except LookupError as exc:
            raise ParseError(f"Unknown text encoding {candidate!r} for {path}.") from exc
        except UnicodeDecodeError as exc:
            last_error = exc
    raise ParseError(f"Could not decode {path} with supported encodings.") from last_error


def reject_nul_characters(text: str, source: str) -> None:
    """Reject text containing NUL characters, a sign of a mis-decoded UTF-16 file."""

    if "\x00" in text:
        line = text.count("\n", 0, text.index("\x00")) + 1
        raise ParseError(
            f"{source} contains a NUL character at line {line}; it may be a UTF-16 file "
            "without byte-order mark. Pass the encoding explicitly, for example "
            "encoding='utf-16-le'."
        )


class _CsvFieldState(Enum):
    FIELD_START = auto()
    UNQUOTED = auto()
    QUOTED = auto()
    AFTER_QUOTE = auto()


@dataclass(slots=True)
class _CsvQuoteScanner:
    """Validate quote placement that ``csv.reader`` otherwise accepts permissively."""

    delimiter: str
    source: str
    state: _CsvFieldState = _CsvFieldState.FIELD_START
    line_number: int = 1
    quote_start_line: int = 1

    def validate(self, text: str) -> None:
        """Validate CSV quoting while retaining physical source line numbers."""

        index = 0
        while index < len(text):
            newline_length = _newline_length(text, index)
            if self.state is _CsvFieldState.QUOTED:
                index = self._consume_quoted(text, index, newline_length)
            elif self.state is _CsvFieldState.AFTER_QUOTE:
                index = self._consume_after_quote(text, index, newline_length)
            elif self.state is _CsvFieldState.FIELD_START:
                index = self._consume_field_start(text, index, newline_length)
            else:
                index = self._consume_unquoted(text, index, newline_length)
        if self.state is _CsvFieldState.QUOTED:
            raise ParseError(
                f"Invalid CSV syntax in {self.source} at line {self.quote_start_line}: "
                "unterminated quoted field."
            )

    def _consume_quoted(self, text: str, index: int, newline_length: int) -> int:
        character = text[index]
        if character == '"':
            if index + 1 < len(text) and text[index + 1] == '"':
                return index + 2
            self.state = _CsvFieldState.AFTER_QUOTE
            return index + 1
        if newline_length:
            self.line_number += 1
            return index + newline_length
        return index + 1

    def _consume_after_quote(self, text: str, index: int, newline_length: int) -> int:
        character = text[index]
        if character == self.delimiter:
            self.state = _CsvFieldState.FIELD_START
            return index + 1
        if newline_length:
            self.state = _CsvFieldState.FIELD_START
            self.line_number += 1
            return index + newline_length
        raise ParseError(
            f"Invalid CSV syntax in {self.source} at line {self.line_number}: "
            "unexpected character after a closing quote."
        )

    def _consume_field_start(self, text: str, index: int, newline_length: int) -> int:
        character = text[index]
        if character == '"':
            self.state = _CsvFieldState.QUOTED
            self.quote_start_line = self.line_number
            return index + 1
        if character == self.delimiter:
            return index + 1
        if newline_length:
            self.line_number += 1
            return index + newline_length
        self.state = _CsvFieldState.UNQUOTED
        return index + 1

    def _consume_unquoted(self, text: str, index: int, newline_length: int) -> int:
        character = text[index]
        if character == '"':
            raise ParseError(
                f"Invalid CSV syntax in {self.source} at line {self.line_number}: "
                "quote inside an unquoted field."
            )
        if character == self.delimiter:
            self.state = _CsvFieldState.FIELD_START
            return index + 1
        if newline_length:
            self.state = _CsvFieldState.FIELD_START
            self.line_number += 1
            return index + newline_length
        return index + 1


def _newline_length(text: str, index: int) -> int:
    character = text[index]
    if character == "\r":
        return 2 if index + 1 < len(text) and text[index + 1] == "\n" else 1
    return 1 if character == "\n" else 0


def parse_rows(text: str, delimiter: str, source: str) -> list[Row]:
    """Parse CSV rows without destroying quoted physical line breaks.

    The character-level quote validation runs only if the text contains a quote
    character; without one there is nothing it could reject.
    """

    if '"' in text:
        _CsvQuoteScanner(delimiter, source).validate(text)
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
    rows: list[Row] = []
    start_line = 1
    try:
        while True:
            start_line = reader.line_num + 1
            rows.append((start_line, next(reader)))
    except StopIteration:
        return rows
    except csv.Error as exc:
        line_number = max(reader.line_num, start_line)
        raise ParseError(f"Invalid CSV syntax in {source} at line {line_number}: {exc}.") from exc


def first_record_fields(text: str, delimiter: str) -> list[str] | None:
    """Split the first physical line with ``delimiter``; ``None`` if that fails."""

    lines = text.splitlines()
    first_record = lines[0] if lines else ""
    try:
        return next(csv.reader([first_record], delimiter=delimiter, strict=True))
    except (csv.Error, StopIteration):
        return None


def normalize_table_shape(rows: list[Row]) -> tuple[list[Row], int]:
    """Drop empty unnamed trailing header columns; return rows and dropped count.

    Data in such a column is an error, because it cannot be attributed to a field.
    """

    if not rows:
        raise ParseError("Input file contains no rows.")
    header = rows[0][1]
    last_named = -1
    for index, value in enumerate(header):
        if clean_header(value):
            last_named = index
    if last_named < 0:
        return rows, 0
    suffix_start = last_named + 1
    if suffix_start == len(header):
        return rows, 0
    for line_number, row in rows[1:]:
        if any(cell.strip() for cell in row[suffix_start:]):
            raise ParseError(f"Unnamed trailing column contains data at line {line_number}.")
    trimmed = [(line, row[:suffix_start]) for line, row in rows]
    return trimmed, len(header) - suffix_start


def clean_header(value: str) -> str:
    """Remove byte-order marks and surrounding whitespace from a header cell."""

    return value.replace("﻿", "").strip()


def normalize_header_key(value: str) -> str:
    """Return a header name compared case- and whitespace-insensitively."""

    return " ".join(str(value).replace("﻿", "").split()).casefold()


def duplicate_names(header: tuple[str, ...]) -> tuple[list[str], tuple[str, str] | None]:
    """Find duplicate column names in one pass, compared as :func:`find_column` does.

    Returns the names that repeat an earlier name except for letter case, and the first
    pair of names that are equal only after runs of whitespace are collapsed
    (``Sample Name``, ``Sample  Name``). Two numbered columns of one family
    (``Allele 1``, ``Allele  1``) are left to :func:`indexed_columns`, whose message
    names the family.
    """

    casefolded: set[str] = set()
    seen: dict[str, str] = {}
    case_duplicates: list[str] = []
    spacing_pair: tuple[str, str] | None = None
    for value in header:
        folded = value.casefold()
        if folded in casefolded:
            case_duplicates.append(value)
            continue
        casefolded.add(folded)
        key = normalize_header_key(value)
        previous = seen.get(key)
        if previous is None:
            seen[key] = value
        elif spacing_pair is None and not (
            _INDEXED_RE.match(previous) and _INDEXED_RE.match(value)
        ):
            spacing_pair = (previous, value)
    return case_duplicates, spacing_pair


def validate_header_names(header: tuple[str, ...]) -> None:
    """Reject an empty header, blank interior names and names repeated except for case."""

    if not any(header):
        raise ParseError("Header row is empty.")
    if any(not value for value in header):
        raise ParseError(
            "Blank column names are not allowed except for empty trailing export columns."
        )
    case_duplicates, _ = duplicate_names(header)
    if case_duplicates:
        raise DuplicateColumnError(f"Duplicate column names: {case_duplicates}")


def reject_spacing_duplicates(header: tuple[str, ...]) -> None:
    """Reject two column names that differ only in spacing (see :func:`duplicate_names`).

    Readers call it after :func:`indexed_columns`, so that numbered families are reported
    with their own message first.
    """

    _, spacing_pair = duplicate_names(header)
    if spacing_pair is not None:
        previous, value = spacing_pair
        raise DuplicateColumnError(
            f"Duplicate column names {previous!r} and {value!r} differ only in spacing."
        )


def find_column(header: tuple[str, ...], requested: str) -> str | None:
    """Return the header column matching ``requested`` case-/space-insensitively."""

    key = normalize_header_key(requested)
    for column in header:
        if normalize_header_key(column) == key:
            return column
    return None


def indexed_columns(header: tuple[str, ...]) -> dict[str, dict[int, str]]:
    """Group numbered columns (``Allele 1``, ``Height 1`` ...) by normalized base name.

    Two columns that differ only in case or spacing of the base name and share an index
    are rejected as semantic duplicates.
    """

    result: dict[str, dict[int, str]] = {}
    for column in header:
        match = _INDEXED_RE.match(column)
        if not match:
            continue
        base = normalize_header_key(match.group("base"))
        if len(match.group("index")) > _MAX_INDEX_DIGITS:
            raise ParseError(
                f"Column {column!r} has a number with more than {_MAX_INDEX_DIGITS} digits."
            )
        index = int(match.group("index"))
        family = result.setdefault(base, {})
        previous = family.get(index)
        if previous is not None:
            raise DuplicateColumnError(
                f"Duplicate semantic indexed column {base!r} {index}: {previous!r} and {column!r}."
            )
        family[index] = column
    return result


def row_mapping(header: tuple[str, ...], raw: list[str], line_number: int) -> dict[str, str]:
    """Pair one row with the header; reject non-empty fields beyond the header."""

    if len(raw) > len(header) and any(cell.strip() for cell in raw[len(header) :]):
        raise ParseError(f"Line {line_number} has non-empty fields beyond the header length.")
    padded = raw[: len(header)] + [""] * max(0, len(header) - len(raw))
    return dict(zip(header, padded, strict=True))


__all__: list[str] = []
