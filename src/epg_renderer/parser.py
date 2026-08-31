"""Schema-aware parser for configurable GeneMapper genotype-table exports.

GeneMapper exports the currently selected table columns rather than one invariant CSV
schema. This module therefore separates delimited-table normalization, header-family
interpretation, sample-injection identity, and row-to-model conversion.
"""

from __future__ import annotations

import csv
import io
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import Enum, auto
from pathlib import Path

from .models import AlleleCall, GeneMapperProject, MarkerCall, SampleCall
from .rfu import MAX_RFU


class GeneMapperParserError(ValueError):
    """Base exception for invalid or unsupported GeneMapper exports."""


class MissingRequiredColumnError(GeneMapperParserError):
    """Raised when a required source column is absent."""


class DuplicateHeaderError(GeneMapperParserError):
    """Raised when the source contains duplicate column names."""


class DuplicateMarkerError(GeneMapperParserError):
    """Raised for duplicate sample-marker rows."""


class NumericConversionError(GeneMapperParserError):
    """Raised when an exported numeric value is malformed."""


_INDEXED_RE = re.compile(r"^(?P<base>.+?)\s+(?P<index>[1-9]\d*)$", re.IGNORECASE)
_DEFAULT_ENCODINGS = ("utf-8-sig", "utf-8", "cp1252", "latin-1")
_SUPPORTED_DELIMITERS = ("\t", ";", ",")
_IDENTITY_COLUMNS = ("Sample Name", "Sample File", "Sample ID", "Run Name")
_INDEXED_ALIASES = {
    "allele": ("allele",),
    "height": ("height",),
    "size": ("size",),
    "area": ("area", "peak area"),
    "mutation": ("mutation",),
    "comment": ("comment",),
}


@dataclass(frozen=True, slots=True)
class _ParserConfig:
    """Column and decoding choices for one parser invocation."""

    source: Path
    sample_id_column: str
    marker_column: str
    dye_column: str | None
    delimiter: str | None
    encoding: str | None
    require_height: bool
    export_mode: str


@dataclass(frozen=True, slots=True)
class _HeaderLayout:
    """Validated source columns and their semantic indexed families."""

    columns: tuple[str, ...]
    sample_id_column: str
    marker_column: str
    dye_column: str | None
    overflow_column: str | None
    identity_columns: dict[str, str]
    indexed_columns: dict[str, dict[int, str]]
    allele_indices: tuple[int, ...]

    def family(self, name: str) -> dict[int, str]:
        """Return one indexed column family by canonical name."""

        return self.indexed_columns.get(name, {})


@dataclass(frozen=True, slots=True)
class _SampleMetadata:
    """Source identity fields shared by all rows of one sample injection."""

    display_name: str
    sample_name: str | None
    sample_file: str | None
    source_sample_id: str | None
    run_name: str | None


@dataclass(slots=True)
class _SampleBucket:
    """Mutable marker collection for one source sample injection."""

    metadata: _SampleMetadata
    markers: dict[str, MarkerCall] = field(default_factory=dict)
    seen_markers: dict[str, tuple[str, int]] = field(default_factory=dict)

    def add(self, marker: str, call: MarkerCall, line_number: int) -> None:
        """Add one marker call while enforcing uniqueness within the injection."""

        marker_key = _normalize_marker_key(marker)
        previous = self.seen_markers.get(marker_key)
        if previous is not None:
            previous_marker, previous_line = previous
            raise DuplicateMarkerError(
                f"Duplicate marker rows {previous_marker!r} (line {previous_line}) and "
                f"{marker!r} (line {line_number}) for sample {self.metadata.display_name!r}."
            )
        self.seen_markers[marker_key] = (marker, line_number)
        self.markers[marker] = call


@dataclass(slots=True)
class _SampleAccumulator:
    """Build immutable samples using source identity rather than display name alone."""

    buckets: dict[tuple[str, ...], _SampleBucket] = field(default_factory=dict)

    def add(
        self,
        identity: tuple[str, ...],
        metadata: _SampleMetadata,
        marker: str,
        call: MarkerCall,
        line_number: int,
    ) -> None:
        """Add one marker row to its stable source-injection bucket."""

        bucket = self.buckets.get(identity)
        if bucket is None:
            bucket = _SampleBucket(metadata)
            self.buckets[identity] = bucket
        elif bucket.metadata != metadata:
            raise GeneMapperParserError(
                f"Inconsistent sample metadata at line {line_number} for "
                f"source identity {identity!r}."
            )
        bucket.add(marker, call, line_number)

    def build(self) -> dict[str, SampleCall]:
        """Create readable unique project identifiers without merging duplicate names."""

        display_counts = Counter(bucket.metadata.display_name for bucket in self.buckets.values())
        samples: dict[str, SampleCall] = {}
        for bucket in self.buckets.values():
            metadata = bucket.metadata
            if display_counts[metadata.display_name] == 1:
                project_id = metadata.display_name
            else:
                discriminator = (
                    metadata.sample_file
                    or metadata.source_sample_id
                    or metadata.run_name
                    or "duplicate"
                )
                project_id = f"{metadata.display_name} [{discriminator}]"
            project_id = _deduplicate_project_id(project_id, samples)
            samples[project_id] = SampleCall(
                project_id,
                bucket.markers,
                display_name=metadata.display_name,
                sample_name=metadata.sample_name,
                sample_file=metadata.sample_file,
                source_sample_id=metadata.source_sample_id,
                run_name=metadata.run_name,
            )
        return samples


class _CsvFieldState(Enum):
    FIELD_START = auto()
    UNQUOTED = auto()
    QUOTED = auto()
    AFTER_QUOTE = auto()


@dataclass(slots=True)
class _CsvQuoteScanner:
    """Validate quote placement that ``csv.reader`` otherwise accepts permissively."""

    delimiter: str
    source: Path
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
            raise GeneMapperParserError(
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
        raise GeneMapperParserError(
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
            raise GeneMapperParserError(
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


def read_genotypes_table(
    path: str | Path,
    *,
    sample_id_column: str = "Sample Name",
    marker_column: str = "Marker",
    dye_column: str | None = "Dye",
    delimiter: str | None = None,
    encoding: str | None = None,
    require_height: bool = True,
    export_mode: str = "unknown",
) -> GeneMapperProject:
    """Parse a configurable GeneMapper Genotypes-table export.

    Indexed fields are paired by numeric suffix. Dye is optional because GeneMapper
    exports only displayed columns; a selected kit supplies missing channel evidence.
    """

    config = _build_parser_config(
        path,
        sample_id_column,
        marker_column,
        dye_column,
        delimiter,
        encoding,
        require_height,
        export_mode,
    )
    return _read_project(config)


def _build_parser_config(
    path: str | Path,
    sample_id_column: str,
    marker_column: str,
    dye_column: str | None,
    delimiter: str | None,
    encoding: str | None,
    require_height: bool,
    export_mode: str,
) -> _ParserConfig:
    mode = str(export_mode).strip().casefold()
    if mode not in {"standard", "with_stutter", "unknown"}:
        raise GeneMapperParserError("export_mode must be standard, with_stutter or unknown.")
    return _ParserConfig(
        Path(path),
        sample_id_column,
        marker_column,
        dye_column,
        delimiter,
        encoding,
        require_height,
        mode,
    )


def _read_project(config: _ParserConfig) -> GeneMapperProject:
    _require_source_file(config.source)
    text, used_encoding = _read_text(config.source, config.encoding)
    used_delimiter = _resolve_delimiter(text, config.delimiter, config.source)
    rows = _parse_csv_rows(text, used_delimiter, config.source)
    rows, shape_warnings = _normalize_table_shape(rows)
    layout = _parse_header(rows[0][1], config)
    samples, parser_warnings = _parse_samples(rows[1:], layout, config)
    return GeneMapperProject(
        samples=samples,
        header=layout.columns,
        delimiter=used_delimiter,
        sample_id_column=layout.sample_id_column,
        source_path=config.source,
        encoding=used_encoding,
        warnings=(*shape_warnings, *parser_warnings),
        export_mode=config.export_mode,
    )


def _require_source_file(source: Path) -> None:
    if not source.is_file():
        raise GeneMapperParserError(f"Input file does not exist: {source}")


def _resolve_delimiter(text: str, delimiter: str | None, source: Path) -> str:
    if not text.strip():
        raise GeneMapperParserError(f"Input file is empty: {source}")
    resolved = delimiter or _detect_delimiter(text)
    if resolved not in _SUPPORTED_DELIMITERS:
        raise GeneMapperParserError(f"Unsupported delimiter: {resolved!r}")
    return resolved


def _normalize_table_shape(
    rows: list[tuple[int, list[str]]],
) -> tuple[list[tuple[int, list[str]]], tuple[str, ...]]:
    if not rows:
        raise GeneMapperParserError("Input file contains no rows.")
    header = rows[0][1]
    last_named = -1
    for index, value in enumerate(header):
        if _clean_header(value):
            last_named = index
    if last_named < 0:
        return rows, ()
    suffix_start = last_named + 1
    if suffix_start == len(header):
        return rows, ()
    for line_number, row in rows[1:]:
        if any(cell.strip() for cell in row[suffix_start:]):
            raise GeneMapperParserError(
                f"Unnamed trailing column contains data at line {line_number}."
            )
    trimmed = [(line, row[:suffix_start]) for line, row in rows]
    count = len(header) - suffix_start
    return trimmed, (f"Ignored {count} empty unnamed trailing column(s).",)


def _parse_header(raw_header: list[str], config: _ParserConfig) -> _HeaderLayout:
    header = tuple(_clean_header(value) for value in raw_header)
    _validate_header_names(header)
    sample_column = _resolve_required_column(header, config.sample_id_column)
    marker_column = _resolve_required_column(header, config.marker_column)
    dye_column = (
        None if config.dye_column is None else _resolve_optional_column(header, config.dye_column)
    )
    overflow_column = _first_optional_column(header, ("Allele Display Overflow", "ADO"))
    indexed = _semantic_indexed_columns(header)
    allele_columns = indexed.get("allele", {})
    height_columns = indexed.get("height", {})
    if not allele_columns:
        raise MissingRequiredColumnError("No columns such as 'Allele 1' were found.")
    if config.require_height and not height_columns:
        raise MissingRequiredColumnError("No columns such as 'Height 1' were found.")
    identity_columns = {
        canonical: actual
        for canonical in _IDENTITY_COLUMNS
        if (actual := _resolve_optional_column(header, canonical)) is not None
    }
    return _HeaderLayout(
        columns=header,
        sample_id_column=sample_column,
        marker_column=marker_column,
        dye_column=dye_column,
        overflow_column=overflow_column,
        identity_columns=identity_columns,
        indexed_columns=indexed,
        allele_indices=tuple(sorted(set().union(*(set(v) for v in indexed.values())))),
    )


def _validate_header_names(header: tuple[str, ...]) -> None:
    if not any(header):
        raise GeneMapperParserError("Header row is empty.")
    if any(not value for value in header):
        raise GeneMapperParserError(
            "Blank column names are not allowed except for empty trailing export columns."
        )
    _reject_duplicate_headers(header)


def _resolve_required_column(header: tuple[str, ...], requested: str) -> str:
    actual = _resolve_optional_column(header, requested)
    if actual is None:
        raise MissingRequiredColumnError(f"Missing required column: {requested!r}")
    return actual


def _resolve_optional_column(header: tuple[str, ...], requested: str) -> str | None:
    key = _normalize_header_key(requested)
    for column in header:
        if _normalize_header_key(column) == key:
            return column
    return None


def _first_optional_column(header: tuple[str, ...], candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        actual = _resolve_optional_column(header, candidate)
        if actual is not None:
            return actual
    return None


def _parse_marker_row(
    raw: list[str],
    line_number: int,
    layout: _HeaderLayout,
    require_height: bool,
) -> tuple[dict[str, str], str, str | None, tuple[AlleleCall, ...]]:
    """Parse one source row without deciding which sample-injection bucket owns it."""

    row = _row_to_mapping(layout.columns, raw, line_number)
    marker = _required_row_value(row, layout.marker_column, line_number, "marker")
    dye = _optional_row_value(row, layout.dye_column)
    alleles = _parse_alleles(row, line_number, marker, layout, require_height)
    return row, marker, dye, alleles


def _parse_samples(
    rows: Iterable[tuple[int, list[str]]],
    layout: _HeaderLayout,
    config: _ParserConfig,
) -> tuple[dict[str, SampleCall], tuple[str, ...]]:
    accumulator = _SampleAccumulator()
    highest_index_used = False
    overflow_lines: list[int] = []
    maximum_allele_index = max(layout.family("allele"), default=0)
    for line_number, raw in rows:
        if not any(cell.strip() for cell in raw):
            continue
        row, marker, dye, alleles = _parse_marker_row(
            raw, line_number, layout, config.require_height
        )
        identity, metadata = _sample_identity(row, layout, config.sample_id_column, line_number)
        if _overflow_is_set(row, layout.overflow_column):
            overflow_lines.append(line_number)
        if maximum_allele_index >= 10 and any(
            call.allele_index == maximum_allele_index for call in alleles
        ):
            highest_index_used = True
        accumulator.add(
            identity,
            metadata,
            marker,
            MarkerCall(marker=marker, dye=dye, alleles=alleles),
            line_number,
        )
    samples = accumulator.build()
    if not samples:
        raise GeneMapperParserError("No sample rows were parsed.")
    warnings: list[str] = []
    if overflow_lines:
        preview = ", ".join(str(value) for value in overflow_lines[:5])
        suffix = "..." if len(overflow_lines) > 5 else ""
        warnings.append(
            "GeneMapper reports allele-display overflow at line(s) "
            f"{preview}{suffix}; exported peak lists may be incomplete."
        )
    elif highest_index_used:
        warnings.append(
            f"Allele {maximum_allele_index} is populated in at least one row; the export "
            "may be truncated if GeneMapper was configured with too few displayed alleles."
        )
    return samples, tuple(warnings)


def _sample_identity(
    row: dict[str, str],
    layout: _HeaderLayout,
    requested_sample_column: str,
    line_number: int,
) -> tuple[tuple[str, ...], _SampleMetadata]:
    requested_value = _required_row_value(
        row,
        layout.sample_id_column,
        line_number,
        f"sample identifier in {layout.sample_id_column!r}",
    )
    values = {
        canonical: _optional_row_value(row, actual)
        for canonical, actual in layout.identity_columns.items()
    }
    sample_name = values.get("Sample Name")
    sample_file = values.get("Sample File")
    source_sample_id = values.get("Sample ID")
    run_name = values.get("Run Name")
    automatic_identity = _normalize_header_key(requested_sample_column) == _normalize_header_key(
        "Sample Name"
    )
    if automatic_identity:
        evidence = tuple(
            value or "" for value in (source_sample_id, run_name, sample_file, sample_name)
        )
        if any(evidence[:3]):
            identity = ("source-injection", *evidence)
        else:
            identity = ("selected-column", requested_value)
    else:
        identity = ("selected-column", requested_value)
    display_name = sample_name or requested_value
    metadata = _SampleMetadata(
        display_name=display_name,
        sample_name=sample_name,
        sample_file=sample_file,
        source_sample_id=source_sample_id,
        run_name=run_name,
    )
    return identity, metadata


def _overflow_is_set(row: dict[str, str], column: str | None) -> bool:
    if column is None:
        return False
    value = row[column].strip().casefold()
    return value not in {"", "0", "false", "no", "n", "none"}


def _deduplicate_project_id(candidate: str, existing: dict[str, SampleCall]) -> str:
    if candidate not in existing:
        return candidate
    counter = 2
    while f"{candidate} #{counter}" in existing:
        counter += 1
    return f"{candidate} #{counter}"


def _required_row_value(
    row: dict[str, str],
    column: str,
    line_number: int,
    description: str,
) -> str:
    value = row[column].strip()
    if not value:
        raise GeneMapperParserError(f"Empty {description} at line {line_number}.")
    return value


def _optional_row_value(row: dict[str, str], column: str | None) -> str | None:
    if column is None:
        return None
    value = row[column].strip()
    return value or None


def _parse_alleles(
    row: dict[str, str],
    line_number: int,
    marker: str,
    layout: _HeaderLayout,
    require_height: bool,
) -> tuple[AlleleCall, ...]:
    alleles: list[AlleleCall] = []
    for index in layout.allele_indices:
        call = _parse_allele_call(row, line_number, marker, index, layout, require_height)
        if call is not None:
            alleles.append(call)
    return tuple(alleles)


def _parse_allele_call(
    row: dict[str, str],
    line_number: int,
    marker: str,
    index: int,
    layout: _HeaderLayout,
    require_height: bool,
) -> AlleleCall | None:
    allele = _indexed_value(row, layout.family("allele"), index)
    raw_height = _indexed_value(row, layout.family("height"), index)
    raw_size = _indexed_value(row, layout.family("size"), index)
    raw_area = _indexed_value(row, layout.family("area"), index)
    mutation = _indexed_value(row, layout.family("mutation"), index) or None
    comment = _indexed_value(row, layout.family("comment"), index) or None
    related_values = (raw_height, raw_size, raw_area, mutation or "", comment or "")
    if not allele and not any(related_values):
        return None
    if not allele:
        raise GeneMapperParserError(
            f"Indexed peak data without allele at line {line_number}, index {index}."
        )
    if not raw_height and require_height:
        raise GeneMapperParserError(
            f"Allele without height at line {line_number}, marker {marker!r}, index {index}."
        )
    height = (
        None if not raw_height else _parse_rfu_integer(raw_height, line_number, f"Height {index}")
    )
    size = None if not raw_size else _parse_decimal(raw_size, line_number, f"Size {index}")
    area = (
        None
        if not raw_area
        else _parse_nonnegative_integer(raw_area, line_number, f"Area {index}", "area")
    )
    return AlleleCall(index, allele, height, size, area, mutation, comment)


def _indexed_value(row: dict[str, str], family: dict[int, str], index: int) -> str:
    column = family.get(index)
    return row.get(column, "").strip() if column else ""


def _read_text(path: Path, encoding: str | None) -> tuple[str, str]:
    candidates = (encoding,) if encoding else _DEFAULT_ENCODINGS
    last_error: UnicodeDecodeError | None = None
    for candidate in candidates:
        assert candidate is not None
        try:
            with path.open("r", encoding=candidate, newline="") as handle:
                return handle.read(), candidate
        except LookupError as exc:
            raise GeneMapperParserError(f"Unknown text encoding {candidate!r} for {path}.") from exc
        except UnicodeDecodeError as exc:
            last_error = exc
    assert last_error is not None
    raise GeneMapperParserError(
        f"Could not decode {path} with supported encodings."
    ) from last_error


def _parse_csv_rows(
    text: str,
    delimiter: str,
    source: Path,
) -> list[tuple[int, list[str]]]:
    """Parse CSV rows without destroying quoted physical line breaks."""

    _CsvQuoteScanner(delimiter, source).validate(text)
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
    rows: list[tuple[int, list[str]]] = []
    start_line = 1
    try:
        while True:
            start_line = reader.line_num + 1
            rows.append((start_line, next(reader)))
    except StopIteration:
        return rows
    except csv.Error as exc:
        line_number = max(reader.line_num, start_line)
        raise GeneMapperParserError(
            f"Invalid CSV syntax in {source} at line {line_number}: {exc}."
        ) from exc


def _newline_length(text: str, index: int) -> int:
    character = text[index]
    if character == "\r":
        return 2 if index + 1 < len(text) and text[index + 1] == "\n" else 1
    return 1 if character == "\n" else 0


def _detect_delimiter(text: str) -> str:
    first_record = text.splitlines()[0] if text.splitlines() else ""
    scores: dict[str, tuple[int, int]] = {}
    for delimiter in _SUPPORTED_DELIMITERS:
        try:
            header = next(csv.reader([first_record], delimiter=delimiter, strict=True))
        except (csv.Error, StopIteration):
            scores[delimiter] = (-1, 0)
            continue
        normalized = tuple(_normalize_header_key(value) for value in header)
        semantic = 0
        semantic += 4 if _normalize_header_key("Marker") in normalized else 0
        has_allele_column = any(re.fullmatch(r"allele\s+[1-9]\d*", value) for value in normalized)
        semantic += 4 if has_allele_column else 0
        semantic += (
            2
            if any(
                _normalize_header_key(candidate) in normalized
                for candidate in ("Sample Name", "Sample ID", "Sample File")
            )
            else 0
        )
        scores[delimiter] = (semantic, len(header))
    delimiter, score = max(scores.items(), key=lambda item: item[1])
    if score[0] <= 0 or score[1] <= 1:
        raise GeneMapperParserError("Could not detect CSV delimiter.")
    return delimiter


def _normalize_marker_key(value: str) -> str:
    return " ".join(value.split()).casefold()


def _normalize_header_key(value: str) -> str:
    return " ".join(str(value).replace("\ufeff", "").split()).casefold()


def _clean_header(value: str) -> str:
    return value.replace("\ufeff", "").strip()


def _reject_duplicate_headers(header: tuple[str, ...]) -> None:
    normalized: dict[str, str] = {}
    duplicates: list[str] = []
    for value in header:
        key = value.casefold()
        if key in normalized:
            duplicates.append(value)
        else:
            normalized[key] = value
    if duplicates:
        raise DuplicateHeaderError(f"Duplicate column names: {duplicates}")


def _semantic_indexed_columns(header: tuple[str, ...]) -> dict[str, dict[int, str]]:
    raw = _indexed_columns(header)
    result: dict[str, dict[int, str]] = {}
    for canonical, aliases in _INDEXED_ALIASES.items():
        merged: dict[int, str] = {}
        for alias in aliases:
            for index, column in raw.get(alias, {}).items():
                previous = merged.get(index)
                if previous is not None:
                    raise DuplicateHeaderError(
                        f"Duplicate semantic indexed column {canonical!r} {index}: "
                        f"{previous!r} and {column!r}."
                    )
                merged[index] = column
        if merged:
            result[canonical] = merged
    return result


def _indexed_columns(header: tuple[str, ...]) -> dict[str, dict[int, str]]:
    result: dict[str, dict[int, str]] = {}
    for column in header:
        match = _INDEXED_RE.match(column)
        if not match:
            continue
        base = _normalize_header_key(match.group("base"))
        index = int(match.group("index"))
        indexed_base = result.setdefault(base, {})
        previous = indexed_base.get(index)
        if previous is not None:
            raise DuplicateHeaderError(
                f"Duplicate semantic indexed column {base!r} {index}: {previous!r} and {column!r}."
            )
        indexed_base[index] = column
    return result


def _row_to_mapping(header: tuple[str, ...], raw: list[str], line_number: int) -> dict[str, str]:
    if len(raw) > len(header) and any(cell.strip() for cell in raw[len(header) :]):
        raise GeneMapperParserError(
            f"Line {line_number} has non-empty fields beyond the header length."
        )
    padded = raw[: len(header)] + [""] * max(0, len(header) - len(raw))
    return dict(zip(header, padded, strict=True))


def _parse_nonnegative_integer(
    value: str,
    line_number: int,
    column: str,
    description: str,
) -> int:
    try:
        if not re.fullmatch(r"[+-]?\d+", value):
            raise ValueError
        parsed = int(value)
    except ValueError as exc:
        raise NumericConversionError(
            f"Invalid integer {description} value {value!r} at line {line_number}, "
            f"column {column!r}."
        ) from exc
    if parsed < 0:
        raise NumericConversionError(
            f"Negative {description} value {parsed} at line {line_number}, column {column!r}."
        )
    return parsed


def _parse_rfu_integer(value: str, line_number: int, column: str) -> int:
    parsed = _parse_nonnegative_integer(value, line_number, column, "RFU")
    if parsed > MAX_RFU:
        raise NumericConversionError(
            f"RFU value at line {line_number}, column {column!r} exceeds "
            f"the supported maximum of {MAX_RFU:,} RFU."
        )
    return parsed


def _parse_decimal(value: str, line_number: int, column: str) -> Decimal:
    try:
        parsed = Decimal(value.replace(",", "."))
    except InvalidOperation as exc:
        raise NumericConversionError(
            f"Invalid decimal size value {value!r} at line {line_number}, column {column!r}."
        ) from exc
    if not parsed.is_finite() or parsed < 0:
        raise NumericConversionError(
            f"Invalid decimal size value {value!r} at line {line_number}, column {column!r}."
        )
    return parsed


__all__ = [
    "DuplicateHeaderError",
    "DuplicateMarkerError",
    "GeneMapperParserError",
    "MissingRequiredColumnError",
    "NumericConversionError",
    "read_genotypes_table",
]
