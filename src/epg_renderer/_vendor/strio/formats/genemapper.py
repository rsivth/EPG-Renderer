"""Reader for GeneMapper genotype-table exports (CSV/TSV).

GeneMapper exports the table columns that are currently displayed, not one fixed
schema. The reader therefore identifies columns by name, never by position:

* ``Allele n``, ``Height n``, ``Size n``, ``Area n`` / ``Peak Area n``,
  ``Mutation n`` and ``Comment n`` are paired by their number ``n``, in any column
  order (``Allele 1, Allele 2, Height 1, Height 2`` or ``Allele 1, Height 1, ...``);
* the sample-identifier column, ``Marker`` and the optional ``Dye`` column are found
  case- and space-insensitively;
* every other column is kept per row in :attr:`strio.Locus.extra`, as text with
  surrounding whitespace removed like every other value.

:attr:`strio.SourceInfo.table` of the result describes the header and delimiter.

The reader is strict: malformed input raises a :class:`strio.ParseError` subclass that
names the line and column. It never repairs or guesses values.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

from ..diagnostics import Diagnostic, DiagnosticCode
from ..errors import (
    DuplicateColumnError,
    DuplicateLocusError,
    MissingColumnError,
    NumericValueError,
    ParseError,
)
from ..model import Allele, Dataset, Locus, Sample, SourceInfo, TableLayout, row_key
from . import _table

FORMAT_NAME = "genemapper-table"
"""Value of :attr:`strio.SourceInfo.format` for datasets read by this module."""

SUPPORTED_DELIMITERS = ("\t", ";", ",")
"""Field delimiters the reader detects or accepts."""

IDENTITY_COLUMNS = ("Sample Name", "Sample File", "Sample ID", "Run Name")
"""Columns that identify one sample injection when present."""

_PEAK_FAMILIES: dict[str, tuple[str, ...]] = {
    "allele": ("allele",),
    "height": ("height",),
    "size": ("size",),
    "area": ("area", "peak area"),
    "mutation": ("mutation",),
    "comment": ("comment",),
}
_OVERFLOW_COLUMNS = ("Allele Display Overflow", "ADO")
_INTEGER_RE = re.compile(r"[+-]?[0-9]+")
_DECIMAL_RE = re.compile(r"[+-]?(?:[0-9]+(?:[.,][0-9]*)?|[.,][0-9]+)")
_SHOWN_VALUE_LENGTH = 40

MAX_INTEGER_DIGITS = 18
"""Most digits (without sign and leading zeros) accepted in a height, an area or the
whole-number part of a size. Larger values cannot come from an instrument export."""

MAX_SIZE_DECIMALS = 6
"""Most digits accepted after the decimal separator of a size, as written (GeneMapper
exports two)."""


@dataclass(frozen=True, slots=True)
class _Options:
    source: str
    path: Path | None
    sample_id_column: str
    marker_column: str
    dye_column: str | None
    delimiter: str | None
    require_height: bool
    max_height: int | None


@dataclass(frozen=True, slots=True)
class _Layout:
    """Validated source columns and how each one is used."""

    columns: tuple[str, ...]
    sample_id_column: str
    marker_column: str
    dye_column: str | None
    overflow_column: str | None
    identity_columns: dict[str, str]
    peak_columns: dict[str, dict[int, str]]
    allele_indices: tuple[int, ...]
    extra_columns: tuple[str, ...]

    def family(self, name: str) -> dict[int, str]:
        return self.peak_columns.get(name, {})


@dataclass(frozen=True, slots=True)
class _Identity:
    display_name: str
    sample_name: str | None
    sample_file: str | None
    source_sample_id: str | None
    run_name: str | None


@dataclass(slots=True)
class _Bucket:
    identity: _Identity
    loci: dict[str, Locus] = field(default_factory=dict)
    seen: dict[str, tuple[str, int]] = field(default_factory=dict)

    def add(self, locus: Locus, line_number: int) -> None:
        key = row_key(locus.marker)
        previous = self.seen.get(key)
        if previous is not None:
            previous_marker, previous_line = previous
            raise DuplicateLocusError(
                f"Duplicate marker rows {previous_marker!r} (line {previous_line}) and "
                f"{locus.marker!r} (line {line_number}) for sample "
                f"{self.identity.display_name!r}."
            )
        self.seen[key] = (locus.marker, line_number)
        self.loci[locus.marker] = locus


@dataclass(slots=True)
class _Accumulator:
    buckets: dict[tuple[str, ...], _Bucket] = field(default_factory=dict)

    def add(
        self, key: tuple[str, ...], identity: _Identity, locus: Locus, line_number: int
    ) -> None:
        bucket = self.buckets.get(key)
        if bucket is None:
            bucket = _Bucket(identity)
            self.buckets[key] = bucket
        elif bucket.identity != identity:
            raise ParseError(
                f"Inconsistent sample metadata at line {line_number} for source identity {key!r}."
            )
        bucket.add(locus, line_number)

    def build(self) -> dict[str, Sample]:
        """Create readable unique identifiers without merging duplicate display names."""

        counts = Counter(bucket.identity.display_name for bucket in self.buckets.values())
        samples: dict[str, Sample] = {}
        for bucket in self.buckets.values():
            identity = bucket.identity
            if counts[identity.display_name] == 1:
                sample_id = identity.display_name
            else:
                discriminator = (
                    identity.sample_file
                    or identity.source_sample_id
                    or identity.run_name
                    or "duplicate"
                )
                sample_id = f"{identity.display_name} [{discriminator}]"
            sample_id = _deduplicate(sample_id, samples)
            samples[sample_id] = Sample(
                sample_id,
                bucket.loci,
                display_name=identity.display_name,
                sample_name=identity.sample_name,
                sample_file=identity.sample_file,
                source_sample_id=identity.source_sample_id,
                run_name=identity.run_name,
            )
        return samples


def read_genemapper(
    path: str | Path,
    *,
    sample_id_column: str = "Sample Name",
    marker_column: str = "Marker",
    dye_column: str | None = "Dye",
    delimiter: str | None = None,
    encoding: str | None = None,
    require_height: bool = True,
    max_height: int | None = None,
) -> Dataset:
    """Read a GeneMapper genotype-table export file.

    Args:
        path: The exported ``.txt``/``.tsv``/``.csv`` file.
        sample_id_column: Column that names the samples. With the default
            ``"Sample Name"``, repeated names stay separate samples when ``Sample ID``,
            ``Run Name`` or ``Sample File`` show that they are different injections.
        marker_column: Column with the marker names.
        dye_column: Optional dye column; ``None`` ignores dyes entirely.
        delimiter: Tab, ``;`` or ``,``; detected from the header when ``None``.
        encoding: Text encoding; detected when ``None`` (see the manual).
        require_height: Reject an allele without ``Height`` (default) or accept it.
        max_height: Optional inclusive upper limit for heights, for example the
            saturation ceiling of an instrument. ``None`` accepts any height.

    Returns:
        The samples in source order, the source description and non-fatal diagnostics.

    Raises:
        strio.ParseError: The file is missing, unreadable or malformed. Subclasses name
            the cause: :class:`strio.MissingColumnError`,
            :class:`strio.DuplicateColumnError`, :class:`strio.DuplicateLocusError`,
            :class:`strio.NumericValueError`.

    """

    source_path = Path(path)
    if not source_path.is_file():
        raise ParseError(f"Input file does not exist: {source_path}")
    _check_max_height(max_height)
    text, used_encoding = _table.read_text(source_path, encoding)
    options = _Options(
        str(source_path),
        source_path,
        sample_id_column,
        marker_column,
        dye_column,
        delimiter,
        require_height,
        max_height,
    )
    return _read(text, used_encoding, options)


def parse_genemapper(
    text: str,
    *,
    source: str = "<text>",
    sample_id_column: str = "Sample Name",
    marker_column: str = "Marker",
    dye_column: str | None = "Dye",
    delimiter: str | None = None,
    require_height: bool = True,
    max_height: int | None = None,
) -> Dataset:
    """Parse the already decoded text of a GeneMapper genotype-table export.

    Behaves exactly like :func:`read_genemapper` except that no file is read and no
    encoding is detected. ``source`` names the text in error messages.
    """

    if not isinstance(text, str):
        raise TypeError(
            f"text must be a str, not {type(text).__name__}; decode bytes first or use "
            "read_genemapper()."
        )
    if not isinstance(source, str):
        raise TypeError(f"source must be a str, not {type(source).__name__}.")
    _check_max_height(max_height)
    options = _Options(
        source,
        None,
        sample_id_column,
        marker_column,
        dye_column,
        delimiter,
        require_height,
        max_height,
    )
    return _read(text, None, options)


def _check_max_height(max_height: int | None) -> None:
    if max_height is not None and (
        isinstance(max_height, bool) or not isinstance(max_height, int) or max_height < 0
    ):
        raise ValueError("max_height must be a non-negative integer or None.")


def _read(text: str, encoding: str | None, options: _Options) -> Dataset:
    _table.reject_nul_characters(text, options.source)
    if not text.strip():
        raise ParseError(f"Input file is empty: {options.source}")
    delimiter = options.delimiter or _detect_delimiter(text)
    if delimiter not in SUPPORTED_DELIMITERS:
        raise ParseError(f"Unsupported delimiter: {delimiter!r}")
    rows = _table.parse_rows(text, delimiter, options.source)
    rows, dropped = _table.normalize_table_shape(rows)
    layout = _parse_header(rows[0][1], options)
    samples, diagnostics = _parse_samples(rows[1:], layout, options)
    if dropped:
        diagnostics.insert(
            0,
            Diagnostic(
                DiagnosticCode.TRAILING_EMPTY_COLUMNS,
                f"Ignored {dropped} empty unnamed trailing column(s).",
            ),
        )
    return Dataset(
        samples,
        SourceInfo(
            FORMAT_NAME,
            path=options.path,
            encoding=encoding,
            table=TableLayout(
                layout.columns,
                delimiter,
                layout.sample_id_column,
                extra_columns=layout.extra_columns,
            ),
        ),
        tuple(diagnostics),
    )


def _detect_delimiter(text: str) -> str:
    scores: dict[str, tuple[int, int]] = {}
    for delimiter in SUPPORTED_DELIMITERS:
        header = _table.first_record_fields(text, delimiter)
        if header is None:
            scores[delimiter] = (-1, 0)
            continue
        normalized = tuple(_table.normalize_header_key(value) for value in header)
        semantic = 0
        semantic += 4 if "marker" in normalized else 0
        has_allele = any(re.fullmatch(r"allele\s+[1-9][0-9]*", value) for value in normalized)
        semantic += 4 if has_allele else 0
        semantic += (
            2
            if any(name in normalized for name in ("sample name", "sample id", "sample file"))
            else 0
        )
        scores[delimiter] = (semantic, len(header))
    delimiter, score = max(scores.items(), key=lambda item: item[1])
    if score[0] <= 0 or score[1] <= 1:
        raise ParseError("Could not detect CSV delimiter.")
    return delimiter


def _parse_header(raw_header: list[str], options: _Options) -> _Layout:
    header = tuple(_table.clean_header(value) for value in raw_header)
    _table.validate_header_names(header)
    sample_column = _required_column(header, options.sample_id_column)
    marker_column = _required_column(header, options.marker_column)
    dye_column = (
        None if options.dye_column is None else _table.find_column(header, options.dye_column)
    )
    overflow_column = next(
        (
            actual
            for candidate in _OVERFLOW_COLUMNS
            if (actual := _table.find_column(header, candidate)) is not None
        ),
        None,
    )
    numbered = _table.indexed_columns(header)
    _table.reject_spacing_duplicates(header)
    peaks = _peak_families(numbered)
    if not peaks.get("allele"):
        raise MissingColumnError("No columns such as 'Allele 1' were found.")
    if options.require_height and not peaks.get("height"):
        raise MissingColumnError("No columns such as 'Height 1' were found.")
    identity_columns = {
        canonical: actual
        for canonical in IDENTITY_COLUMNS
        if (actual := _table.find_column(header, canonical)) is not None
    }
    consumed = {sample_column, marker_column, *identity_columns.values()}
    if dye_column is not None:
        consumed.add(dye_column)
    for family in peaks.values():
        consumed.update(family.values())
    return _Layout(
        columns=header,
        sample_id_column=sample_column,
        marker_column=marker_column,
        dye_column=dye_column,
        overflow_column=overflow_column,
        identity_columns=identity_columns,
        peak_columns=peaks,
        allele_indices=tuple(sorted(set().union(*(set(f) for f in peaks.values())))),
        extra_columns=tuple(column for column in header if column not in consumed),
    )


def _required_column(header: tuple[str, ...], requested: str) -> str:
    actual = _table.find_column(header, requested)
    if actual is None:
        raise MissingColumnError(f"Missing required column: {requested!r}")
    return actual


def _peak_families(numbered: dict[str, dict[int, str]]) -> dict[str, dict[int, str]]:
    result: dict[str, dict[int, str]] = {}
    for canonical, aliases in _PEAK_FAMILIES.items():
        merged: dict[int, str] = {}
        for alias in aliases:
            for index, column in numbered.get(alias, {}).items():
                previous = merged.get(index)
                if previous is not None:
                    raise DuplicateColumnError(
                        f"Duplicate semantic indexed column {canonical!r} {index}: "
                        f"{previous!r} and {column!r}."
                    )
                merged[index] = column
        if merged:
            result[canonical] = merged
    return result


def _parse_samples(
    rows: Iterable[_table.Row], layout: _Layout, options: _Options
) -> tuple[dict[str, Sample], list[Diagnostic]]:
    accumulator = _Accumulator()
    highest_index_used = False
    overflow_lines: list[int] = []
    highest_lines: list[int] = []
    maximum_allele_index = max(layout.family("allele"), default=0)
    for line_number, raw in rows:
        if not any(cell.strip() for cell in raw):
            continue
        row = _table.row_mapping(layout.columns, raw, line_number)
        marker = _required_value(row, layout.marker_column, line_number, "marker")
        alleles = tuple(_parse_alleles(row, line_number, marker, layout, options))
        key, identity = _sample_identity(row, layout, options.sample_id_column, line_number)
        if _overflow_is_set(row, layout.overflow_column):
            overflow_lines.append(line_number)
        if maximum_allele_index >= 10 and any(
            allele.index == maximum_allele_index for allele in alleles
        ):
            highest_index_used = True
            highest_lines.append(line_number)
        locus = Locus(
            marker,
            _optional_value(row, layout.dye_column),
            alleles,
            extra={column: row[column].strip() for column in layout.extra_columns},
            line=line_number,
        )
        accumulator.add(key, identity, locus, line_number)
    samples = accumulator.build()
    if not samples:
        raise ParseError("No sample rows were parsed.")
    diagnostics: list[Diagnostic] = []
    if overflow_lines:
        preview = ", ".join(str(value) for value in overflow_lines[:5])
        suffix = "..." if len(overflow_lines) > 5 else ""
        diagnostics.append(
            Diagnostic(
                DiagnosticCode.ALLELE_DISPLAY_OVERFLOW,
                "GeneMapper reports allele-display overflow at line(s) "
                f"{preview}{suffix}; exported peak lists may be incomplete.",
                tuple(overflow_lines),
            )
        )
    elif highest_index_used:
        diagnostics.append(
            Diagnostic(
                DiagnosticCode.HIGHEST_ALLELE_COLUMN_USED,
                f"Allele {maximum_allele_index} is populated in at least one row; the export "
                "may be truncated if GeneMapper was configured with too few displayed alleles.",
                tuple(highest_lines),
            )
        )
    return samples, diagnostics


def _sample_identity(
    row: dict[str, str], layout: _Layout, requested_column: str, line_number: int
) -> tuple[tuple[str, ...], _Identity]:
    requested_value = _required_value(
        row,
        layout.sample_id_column,
        line_number,
        f"sample identifier in {layout.sample_id_column!r}",
    )
    values = {
        canonical: _optional_value(row, actual)
        for canonical, actual in layout.identity_columns.items()
    }
    sample_name = values.get("Sample Name")
    sample_file = values.get("Sample File")
    source_sample_id = values.get("Sample ID")
    run_name = values.get("Run Name")
    automatic = _table.normalize_header_key(requested_column) == "sample name"
    evidence = tuple(
        value or "" for value in (source_sample_id, run_name, sample_file, sample_name)
    )
    if automatic and any(evidence[:3]):
        key: tuple[str, ...] = ("source-injection", *evidence)
    else:
        key = ("selected-column", requested_value)
    identity = _Identity(
        display_name=sample_name or requested_value,
        sample_name=sample_name,
        sample_file=sample_file,
        source_sample_id=source_sample_id,
        run_name=run_name,
    )
    return key, identity


def _overflow_is_set(row: dict[str, str], column: str | None) -> bool:
    if column is None:
        return False
    return row[column].strip().casefold() not in {"", "0", "false", "no", "n", "none"}


def _deduplicate(candidate: str, existing: dict[str, Sample]) -> str:
    if candidate not in existing:
        return candidate
    counter = 2
    while f"{candidate} #{counter}" in existing:
        counter += 1
    return f"{candidate} #{counter}"


def _required_value(row: dict[str, str], column: str, line_number: int, description: str) -> str:
    value = row[column].strip()
    if not value:
        raise ParseError(f"Empty {description} at line {line_number}.")
    return value


def _optional_value(row: dict[str, str], column: str | None) -> str | None:
    if column is None:
        return None
    return row[column].strip() or None


def _parse_alleles(
    row: dict[str, str], line_number: int, marker: str, layout: _Layout, options: _Options
) -> Iterable[Allele]:
    for index in layout.allele_indices:
        allele = _parse_allele(row, line_number, marker, index, layout, options)
        if allele is not None:
            yield allele


def _parse_allele(
    row: dict[str, str],
    line_number: int,
    marker: str,
    index: int,
    layout: _Layout,
    options: _Options,
) -> Allele | None:
    label = _indexed_value(row, layout.family("allele"), index)
    raw_height = _indexed_value(row, layout.family("height"), index)
    raw_size = _indexed_value(row, layout.family("size"), index)
    raw_area = _indexed_value(row, layout.family("area"), index)
    mutation = _indexed_value(row, layout.family("mutation"), index) or None
    comment = _indexed_value(row, layout.family("comment"), index) or None
    if not label and not any((raw_height, raw_size, raw_area, mutation, comment)):
        return None
    if not label:
        raise ParseError(f"Indexed peak data without allele at line {line_number}, index {index}.")
    if not raw_height and options.require_height:
        raise ParseError(
            f"Allele without height at line {line_number}, marker {marker!r}, index {index}."
        )
    height = (
        None
        if not raw_height
        else _parse_height(
            raw_height, line_number, layout.family("height")[index], options.max_height
        )
    )
    size = (
        None if not raw_size else _parse_size(raw_size, line_number, layout.family("size")[index])
    )
    area = (
        None
        if not raw_area
        else _parse_nonnegative_integer(raw_area, line_number, layout.family("area")[index], "area")
    )
    return Allele(index, label, height, size, area, mutation, comment)


def _indexed_value(row: dict[str, str], family: dict[int, str], index: int) -> str:
    column = family.get(index)
    return row.get(column, "").strip() if column else ""


def _shown(value: str) -> str:
    """Quote a value for an error message, shortening very long values."""

    if len(value) <= _SHOWN_VALUE_LENGTH:
        return repr(value)
    return f"{value[:_SHOWN_VALUE_LENGTH]!r}... ({len(value)} characters)"


def _check_digit_count(digits: str, value: str, line_number: int, column: str, what: str) -> None:
    if len(digits.lstrip("0")) > MAX_INTEGER_DIGITS:
        raise NumericValueError(
            f"{what} {_shown(value)} at line {line_number}, column {column!r} has more than "
            f"{MAX_INTEGER_DIGITS} digits."
        )


def _parse_nonnegative_integer(value: str, line_number: int, column: str, description: str) -> int:
    if not _INTEGER_RE.fullmatch(value):
        raise NumericValueError(
            f"Invalid integer {description} value {_shown(value)} at line {line_number}, "
            f"column {column!r}."
        )
    _check_digit_count(
        value.lstrip("+-"), value, line_number, column, f"Integer {description} value"
    )
    parsed = int(value)
    if parsed < 0:
        raise NumericValueError(
            f"Negative {description} value {parsed} at line {line_number}, column {column!r}."
        )
    return parsed


def _parse_height(value: str, line_number: int, column: str, maximum: int | None) -> int:
    if maximum is not None and _INTEGER_RE.fullmatch(value):
        digits = value.lstrip("+-").lstrip("0")
        if not value.startswith("-") and len(digits) > len(str(maximum)):
            raise NumericValueError(_height_limit_message(line_number, column, maximum))
    parsed = _parse_nonnegative_integer(value, line_number, column, "RFU")
    if maximum is not None and parsed > maximum:
        raise NumericValueError(_height_limit_message(line_number, column, maximum))
    return parsed


def _height_limit_message(line_number: int, column: str, maximum: int) -> str:
    return (
        f"RFU value at line {line_number}, column {column!r} exceeds "
        f"the supported maximum of {maximum:,} RFU."
    )


def _parse_size(value: str, line_number: int, column: str) -> Decimal:
    message = (
        f"Invalid decimal size value {_shown(value)} at line {line_number}, column {column!r}."
    )
    if not _DECIMAL_RE.fullmatch(value):
        raise NumericValueError(message)
    whole_part, _, fraction = value.lstrip("+-").replace(",", ".").partition(".")
    _check_digit_count(whole_part, value, line_number, column, "Size value")
    if len(fraction) > MAX_SIZE_DECIMALS:
        raise NumericValueError(
            f"Size value {_shown(value)} at line {line_number}, column {column!r} has more "
            f"than {MAX_SIZE_DECIMALS} decimal places."
        )
    try:
        parsed = Decimal(value.replace(",", "."))
    except InvalidOperation as exc:
        raise NumericValueError(message) from exc
    if parsed < 0:
        raise NumericValueError(message)
    return parsed


__all__ = [
    "FORMAT_NAME",
    "IDENTITY_COLUMNS",
    "SUPPORTED_DELIMITERS",
    "parse_genemapper",
    "read_genemapper",
]
