"""Immutable, format-neutral data model for STR typing results.

The model has four levels, mirroring how CE analysis software exports results::

    Dataset ─ Sample ─ Locus ─ Allele

Every object is a frozen dataclass whose constructor validates its invariants and
copies mutable inputs, so a model that exists is always internally consistent. Text
fields accept only ``str`` (``TypeError`` otherwise); nothing is converted silently.
Measurements that a file does not contain are ``None``; they are never replaced by
zero. Columns a reader does not interpret are kept verbatim in ``extra`` mappings.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from os import PathLike
from pathlib import Path
from types import MappingProxyType
from typing import TypeVar

from .alleles import AlleleValue, parse_allele_label
from .diagnostics import Diagnostic
from .errors import InconsistentExtraError
from .markers import marker_key

_K = TypeVar("_K")
_V = TypeVar("_V")


def _frozen_mapping(values: Mapping[_K, _V]) -> Mapping[_K, _V]:
    """Copy a mapping into a read-only, insertion-ordered view."""

    return MappingProxyType(dict(values))


def _require_str(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a str, not {type(value).__name__}.")
    return value


def _optional_text(value: object, field_name: str) -> str | None:
    """Strip optional text and turn blank text into ``None``; reject non-strings."""

    if value is None:
        return None
    text = _require_str(value, field_name).strip()
    return text or None


def _required_text(value: object, field_name: str) -> str:
    text = _require_str(value, field_name).strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty.")
    return text


def _text_tuple(values: Iterable[object], field_name: str) -> tuple[str, ...]:
    if isinstance(values, str):
        raise TypeError(f"{field_name} must be a sequence of str, not a single str.")
    return tuple(_require_str(item, f"{field_name} item") for item in values)


def _extra_mapping(values: Mapping[str, str], owner: str) -> Mapping[str, str]:
    copied: dict[str, str] = {}
    for key, value in dict(values).items():
        _require_str(key, f"{owner} extra key")
        if not key.strip():
            raise ValueError(f"{owner} extra keys must be non-empty strings.")
        if not isinstance(value, str):
            raise TypeError(f"{owner} extra values must be strings.")
        copied[key] = value
    return MappingProxyType(copied)


def _optional_nonnegative_int(value: object, field_name: str) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer or None.")


def row_key(marker: str) -> str:
    """Return the key under which two marker rows count as duplicates.

    Letter case and runs of whitespace are ignored; synonyms are not resolved. This is
    deliberately narrower than :func:`strio.marker_key`.
    """

    return " ".join(marker.split()).casefold()


@dataclass(frozen=True, slots=True)
class Allele:
    """One exported allele call of a locus and its optional measurements.

    ``index`` is the allele's column number in the source (``Allele 3`` -> ``3``).
    ``label`` is the exported text and stays authoritative; ``value`` is its derived,
    conservative interpretation (see :func:`strio.parse_allele_label`).
    """

    index: int
    label: str
    height: int | None = None
    size_bp: Decimal | None = None
    area: int | None = None
    mutation: str | None = None
    comment: str | None = None
    value: AlleleValue = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.index, bool) or not isinstance(self.index, int) or self.index < 1:
            raise ValueError("index must be a positive integer.")
        label = _required_text(self.label, "label")
        _optional_nonnegative_int(self.height, "height")
        _optional_nonnegative_int(self.area, "area")
        size = self.size_bp
        if size is not None:
            if isinstance(size, bool) or not isinstance(size, Decimal | int | str):
                raise TypeError(
                    "size_bp must be a Decimal, an int or a decimal str, "
                    f"not {type(size).__name__}."
                )
            try:
                size = Decimal(size)
            except InvalidOperation as exc:
                raise ValueError("size_bp must be a finite non-negative decimal or None.") from exc
            if not size.is_finite() or size < 0:
                raise ValueError("size_bp must be a finite non-negative decimal or None.")
        object.__setattr__(self, "label", label)
        object.__setattr__(self, "size_bp", size)
        object.__setattr__(self, "mutation", _optional_text(self.mutation, "mutation"))
        object.__setattr__(self, "comment", _optional_text(self.comment, "comment"))
        object.__setattr__(self, "value", parse_allele_label(label))


@dataclass(frozen=True, slots=True)
class Locus:
    """All exported allele calls of one marker row of one sample.

    ``marker`` is the name as exported; ``key`` is its canonical lookup key (see
    :func:`strio.marker_key`). ``line`` is the 1-based source line of the row.
    """

    marker: str
    dye: str | None
    alleles: tuple[Allele, ...]
    extra: Mapping[str, str] = field(default_factory=dict)
    line: int | None = None
    key: str = field(init=False)

    def __post_init__(self) -> None:
        marker = _required_text(self.marker, "marker")
        alleles = tuple(self.alleles)
        if any(not isinstance(allele, Allele) for allele in alleles):
            raise TypeError("alleles must contain Allele objects.")
        indexes = tuple(allele.index for allele in alleles)
        if indexes != tuple(sorted(indexes)) or len(indexes) != len(set(indexes)):
            raise ValueError("Allele indexes must be unique and strictly increasing.")
        if self.line is not None and (
            isinstance(self.line, bool) or not isinstance(self.line, int) or self.line < 1
        ):
            raise ValueError("line must be a positive integer or None.")
        object.__setattr__(self, "marker", marker)
        object.__setattr__(self, "dye", _optional_text(self.dye, "dye"))
        object.__setattr__(self, "alleles", alleles)
        object.__setattr__(self, "extra", _extra_mapping(self.extra, "Locus"))
        object.__setattr__(self, "key", marker_key(marker))

    @property
    def labels(self) -> tuple[str, ...]:
        """Return the exported allele labels in source order."""

        return tuple(allele.label for allele in self.alleles)

    def indexed_extra(self, base: str, index: int) -> str:
        """Return the extra value of the numbered column ``"<base> <index>"``.

        Numbered columns that STRio does not interpret (for example ``Data Point 3``)
        are kept in :attr:`extra` under their exported names. This helper finds one of
        them for an allele index, ignoring letter case and runs of whitespace, so
        ``locus.indexed_extra("Data Point", allele.index)`` pairs it with its allele.
        Raises ``KeyError`` if the row has no such column.
        """

        wanted = row_key(f"{base} {index}")
        for column, value in self.extra.items():
            if row_key(column) == wanted:
                return value
        raise KeyError(f"Locus {self.marker!r} has no extra column {base!r} {index}.")


@dataclass(frozen=True, slots=True)
class Sample:
    """All loci of one sample injection, in source order.

    ``id`` is unique within its :class:`Dataset`. ``display_name`` is the name a person
    would recognise (normally the exported Sample Name). The remaining identity fields
    are copied from the source when present and are ``None`` otherwise.
    """

    id: str
    loci: Mapping[str, Locus] = field(default_factory=dict)
    display_name: str | None = None
    sample_name: str | None = None
    sample_file: str | None = None
    source_sample_id: str | None = None
    run_name: str | None = None

    def __post_init__(self) -> None:
        sample_id = _required_text(self.id, "id")
        copied = dict(self.loci)
        seen: dict[str, str] = {}
        for name, locus in copied.items():
            if not isinstance(locus, Locus):
                raise TypeError("loci must map marker names to Locus objects.")
            if name != locus.marker:
                raise ValueError(
                    f"Locus mapping key {name!r} does not match marker {locus.marker!r}."
                )
            duplicate = seen.get(row_key(name))
            if duplicate is not None:
                raise ValueError(f"Duplicate loci {duplicate!r} and {name!r}.")
            seen[row_key(name)] = name
        object.__setattr__(self, "id", sample_id)
        object.__setattr__(self, "loci", _frozen_mapping(copied))
        display_name = _optional_text(self.display_name, "display_name") or sample_id
        object.__setattr__(self, "display_name", display_name)
        for name in ("sample_name", "sample_file", "source_sample_id", "run_name"):
            object.__setattr__(self, name, _optional_text(getattr(self, name), name))

    def locus(self, name: str) -> Locus:
        """Return the locus whose canonical key matches ``name``.

        ``sample.locus("vwa")`` finds a row exported as ``vWA``. Raises ``KeyError`` if
        no locus matches and ``LookupError`` if several loci share the key (for example
        rows exported as both ``AM`` and ``Amelogenin``).
        """

        key = marker_key(name)
        matches = [locus for locus in self.loci.values() if locus.key == key]
        if not matches:
            raise KeyError(f"Sample {self.id!r} has no locus {name!r}.")
        if len(matches) > 1:
            names = ", ".join(repr(locus.marker) for locus in matches)
            raise LookupError(f"Locus {name!r} is ambiguous in sample {self.id!r}: {names}.")
        return matches[0]

    def has_locus(self, name: str) -> bool:
        """Return whether exactly one locus matches ``name`` by canonical key."""

        try:
            self.locus(name)
        except LookupError:
            return False
        return True

    def common_extra(self, column: str) -> str:
        """Return the value of a row-level extra column that is the same in every row.

        Use it for columns that describe the whole injection, such as ``Panel`` or
        ``Sample Type``. Raises ``KeyError`` if no row has the column and
        :class:`strio.InconsistentExtraError` if the rows disagree.
        """

        values = [locus.extra[column] for locus in self.loci.values() if column in locus.extra]
        if not values:
            raise KeyError(f"Sample {self.id!r} has no extra column {column!r}.")
        if len(values) != len(self.loci) or len(set(values)) != 1:
            distinct = sorted(set(values))
            raise InconsistentExtraError(
                f"Extra column {column!r} differs between rows of sample {self.id!r}: {distinct}."
            )
        return values[0]


@dataclass(frozen=True, slots=True)
class TableLayout:
    """How a delimited table was laid out: its header, delimiter and column roles.

    Readers of tabular formats (GeneMapper) fill it; readers of other formats leave
    :attr:`SourceInfo.table` empty. ``extra_columns`` lists, in header order, the columns
    whose values are kept in :attr:`Locus.extra`.
    """

    header: tuple[str, ...]
    delimiter: str
    sample_id_column: str
    extra_columns: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        header = _text_tuple(self.header, "header")
        if not header or any(not value.strip() for value in header):
            raise ValueError("header must contain non-empty column names.")
        delimiter = _require_str(self.delimiter, "delimiter")
        if len(delimiter) != 1:
            raise ValueError("delimiter must be exactly one character.")
        sample_id_column = _required_text(self.sample_id_column, "sample_id_column")
        if sample_id_column not in header:
            raise ValueError(f"sample_id_column {sample_id_column!r} is not in the header.")
        extra_columns = _text_tuple(self.extra_columns, "extra_columns")
        unknown = [column for column in extra_columns if column not in header]
        if unknown:
            raise ValueError(f"extra_columns are not in the header: {unknown}.")
        object.__setattr__(self, "header", header)
        object.__setattr__(self, "sample_id_column", sample_id_column)
        object.__setattr__(self, "extra_columns", extra_columns)


@dataclass(frozen=True, slots=True)
class SourceInfo:
    """Where a dataset came from and how it was read, independent of the file format.

    ``format`` names the reader (for example ``"genemapper-table"``). ``table`` holds the
    layout of tabular sources and is ``None`` for other formats.
    """

    format: str
    path: Path | None = None
    encoding: str | None = None
    table: TableLayout | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "format", _required_text(self.format, "format"))
        if self.path is not None:
            if not isinstance(self.path, str | PathLike):
                raise TypeError(f"path must be a str or a path, not {type(self.path).__name__}.")
            object.__setattr__(self, "path", Path(self.path))
        if self.encoding is not None:
            object.__setattr__(self, "encoding", _required_text(self.encoding, "encoding"))
        if self.table is not None and not isinstance(self.table, TableLayout):
            raise TypeError("table must be a TableLayout or None.")

    def require_table(self) -> TableLayout:
        """Return :attr:`table`, or raise ``ValueError`` for a source without one."""

        if self.table is None:
            raise ValueError(f"Source format {self.format!r} has no table layout.")
        return self.table


@dataclass(frozen=True, slots=True)
class Dataset:
    """The samples of one source file, its provenance and non-fatal findings."""

    samples: Mapping[str, Sample]
    source: SourceInfo
    diagnostics: tuple[Diagnostic, ...] = ()

    def __post_init__(self) -> None:
        copied = dict(self.samples)
        for sample_id, sample in copied.items():
            if not isinstance(sample, Sample):
                raise TypeError("samples must map identifiers to Sample objects.")
            if sample_id != sample.id:
                raise ValueError(
                    f"Sample mapping key {sample_id!r} does not match sample id {sample.id!r}."
                )
        if not isinstance(self.source, SourceInfo):
            raise TypeError("source must be a SourceInfo object.")
        diagnostics = tuple(self.diagnostics)
        if any(not isinstance(item, Diagnostic) for item in diagnostics):
            raise TypeError("diagnostics must contain Diagnostic objects.")
        object.__setattr__(self, "samples", _frozen_mapping(copied))
        object.__setattr__(self, "diagnostics", diagnostics)

    @property
    def sample_ids(self) -> tuple[str, ...]:
        """Return the sample identifiers in source order."""

        return tuple(self.samples)

    def sample(self, sample_id: str) -> Sample:
        """Return one sample by its exact identifier."""

        return self.samples[sample_id]

    @property
    def messages(self) -> tuple[str, ...]:
        """Return the diagnostic messages as plain text, in order."""

        return tuple(item.message for item in self.diagnostics)


__all__ = ["Allele", "Dataset", "Locus", "Sample", "SourceInfo", "TableLayout", "row_key"]
