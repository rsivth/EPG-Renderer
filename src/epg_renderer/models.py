"""Immutable data structures for normalized allele-call profiles."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import MappingProxyType
from typing import TypeVar

from .domain import PeakHeightMode, ProfileOrigin
from .rfu import validate_rfu

_K = TypeVar("_K")
_V = TypeVar("_V")


def _immutable_mapping(values: Mapping[_K, _V]) -> Mapping[_K, _V]:
    """Copy a mapping and expose it through a read-only insertion-ordered view."""

    return MappingProxyType(dict(values))


def _optional_text(value: str | None) -> str | None:
    """Normalize optional exported text without turning missing data into evidence."""

    if value is None:
        return None
    text = str(value).strip()
    return text or None


@dataclass(frozen=True, slots=True)
class AlleleCall:
    """One indexed exported peak and its optional GeneMapper measurements."""

    allele_index: int
    allele: str
    height: int | None
    size_bp: Decimal | None = None
    area: int | None = None
    mutation: str | None = None
    comment: str | None = None

    def __post_init__(self) -> None:
        if (
            isinstance(self.allele_index, bool)
            or not isinstance(self.allele_index, int)
            or self.allele_index < 1
        ):
            raise ValueError("allele_index must be a positive integer.")
        allele = str(self.allele).strip()
        if not allele:
            raise ValueError("allele must not be empty.")
        if self.height is not None:
            validate_rfu(self.height, allow_zero=True)
        size = self.size_bp
        if size is not None:
            try:
                size = Decimal(str(size))
            except InvalidOperation as exc:
                raise ValueError("size_bp must be a finite non-negative decimal or None.") from exc
            if not size.is_finite() or size < 0:
                raise ValueError("size_bp must be a finite non-negative decimal or None.")
        if self.area is not None and (
            isinstance(self.area, bool) or not isinstance(self.area, int) or self.area < 0
        ):
            raise ValueError("area must be a non-negative integer or None.")
        object.__setattr__(self, "allele", allele)
        object.__setattr__(self, "size_bp", size)
        object.__setattr__(self, "mutation", _optional_text(self.mutation))
        object.__setattr__(self, "comment", _optional_text(self.comment))


@dataclass(frozen=True, slots=True)
class MarkerCall:
    """All exported peaks for one marker row."""

    marker: str
    dye: str | None
    alleles: tuple[AlleleCall, ...]

    def __post_init__(self) -> None:
        marker = str(self.marker).strip()
        if not marker:
            raise ValueError("marker must not be empty.")
        dye = _optional_text(self.dye)
        alleles = tuple(self.alleles)
        indexes = tuple(call.allele_index for call in alleles)
        if indexes != tuple(sorted(indexes)) or len(indexes) != len(set(indexes)):
            raise ValueError("Allele indexes must be unique and strictly increasing.")
        object.__setattr__(self, "marker", marker)
        object.__setattr__(self, "dye", dye)
        object.__setattr__(self, "alleles", alleles)


@dataclass(frozen=True, slots=True)
class SampleCall:
    """All marker calls for one sample injection, preserving source row order."""

    sample_id: str
    markers: Mapping[str, MarkerCall] = field(default_factory=dict)
    display_name: str | None = None
    sample_name: str | None = None
    sample_file: str | None = None
    source_sample_id: str | None = None
    run_name: str | None = None
    origin: ProfileOrigin = ProfileOrigin.GENEMAPPER
    height_mode: PeakHeightMode = PeakHeightMode.RFU

    def __post_init__(self) -> None:
        sample_id = str(self.sample_id).strip()
        if not sample_id:
            raise ValueError("sample_id must not be empty.")
        copied = dict(self.markers)
        for marker_name, marker_call in copied.items():
            if marker_name != marker_call.marker:
                raise ValueError(
                    f"Marker mapping key {marker_name!r} does not match call "
                    f"name {marker_call.marker!r}."
                )
        if not isinstance(self.origin, ProfileOrigin):
            raise TypeError("origin must be a ProfileOrigin value.")
        if not isinstance(self.height_mode, PeakHeightMode):
            raise TypeError("height_mode must be a PeakHeightMode value.")
        display_name = _optional_text(self.display_name) or sample_id
        object.__setattr__(self, "sample_id", sample_id)
        object.__setattr__(self, "markers", _immutable_mapping(copied))
        object.__setattr__(self, "display_name", display_name)
        object.__setattr__(self, "sample_name", _optional_text(self.sample_name))
        object.__setattr__(self, "sample_file", _optional_text(self.sample_file))
        object.__setattr__(self, "source_sample_id", _optional_text(self.source_sample_id))
        object.__setattr__(self, "run_name", _optional_text(self.run_name))


@dataclass(frozen=True, slots=True)
class GeneMapperProject:
    """Normalized immutable representation of one GeneMapper genotype-table export."""

    samples: Mapping[str, SampleCall]
    header: tuple[str, ...]
    delimiter: str
    sample_id_column: str
    source_path: Path | None = None
    encoding: str | None = None
    warnings: tuple[str, ...] = ()
    export_mode: str = "unknown"

    def __post_init__(self) -> None:
        copied = dict(self.samples)
        for sample_id, sample in copied.items():
            if sample_id != sample.sample_id:
                raise ValueError(
                    f"Sample mapping key {sample_id!r} does not match sample "
                    f"identifier {sample.sample_id!r}."
                )
        header = tuple(str(value) for value in self.header)
        if not header or any(not value.strip() for value in header):
            raise ValueError("header must contain non-empty column names.")
        delimiter = str(self.delimiter)
        if len(delimiter) != 1:
            raise ValueError("delimiter must be exactly one character.")
        sample_id_column = str(self.sample_id_column).strip()
        if not sample_id_column:
            raise ValueError("sample_id_column must not be empty.")
        export_mode = str(self.export_mode).strip().casefold()
        if export_mode not in {"standard", "with_stutter", "unknown"}:
            raise ValueError("export_mode must be standard, with_stutter or unknown.")
        object.__setattr__(self, "samples", _immutable_mapping(copied))
        object.__setattr__(self, "header", header)
        object.__setattr__(self, "delimiter", delimiter)
        object.__setattr__(self, "sample_id_column", sample_id_column)
        object.__setattr__(self, "warnings", tuple(str(value) for value in self.warnings))
        object.__setattr__(self, "export_mode", export_mode)
        if self.source_path is not None:
            object.__setattr__(self, "source_path", Path(self.source_path))

    @property
    def sample_ids(self) -> tuple[str, ...]:
        """Return stable, presentation-safe sample identifiers in source order."""

        return tuple(self.samples)

    def sample(self, sample_id: str) -> SampleCall:
        """Return one sample by its exact project identifier."""

        return self.samples[sample_id]


__all__ = ["AlleleCall", "GeneMapperProject", "MarkerCall", "SampleCall"]
