"""GeneMapper genotype-table import.

Reading is done by the bundled STRio reader (``epg_renderer._vendor.strio``), which
applies EPG-Renderer's input contract: indexed column families paired by number,
strict CSV quoting, source-injection identity and line-precise errors. This module keeps
the renderer's side of that contract: it validates ``export_mode``, applies the shared
32,767-RFU ceiling, converts the result into the renderer's immutable call models and
raises the renderer's exception classes with the reader's messages.
"""

from __future__ import annotations

from pathlib import Path

from ._vendor import strio
from .models import AlleleCall, GeneMapperProject, MarkerCall, SampleCall
from .rfu import MAX_RFU


class GeneMapperParserError(strio.ParseError):
    """Base exception for invalid or unsupported GeneMapper exports."""


class MissingRequiredColumnError(GeneMapperParserError, strio.MissingColumnError):
    """Raised when a required source column is absent."""


class DuplicateHeaderError(GeneMapperParserError, strio.DuplicateColumnError):
    """Raised when the source contains duplicate column names."""


class DuplicateMarkerError(GeneMapperParserError, strio.DuplicateLocusError):
    """Raised for duplicate sample-marker rows."""


class NumericConversionError(GeneMapperParserError, strio.NumericValueError):
    """Raised when an exported numeric value is malformed."""


_EXPORT_MODES = frozenset({"standard", "with_stutter", "unknown"})
_ERROR_TYPES: tuple[tuple[type[strio.ParseError], type[GeneMapperParserError]], ...] = (
    (strio.MissingColumnError, MissingRequiredColumnError),
    (strio.DuplicateColumnError, DuplicateHeaderError),
    (strio.DuplicateLocusError, DuplicateMarkerError),
    (strio.NumericValueError, NumericConversionError),
)


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

    mode = str(export_mode).strip().casefold()
    if mode not in _EXPORT_MODES:
        raise GeneMapperParserError("export_mode must be standard, with_stutter or unknown.")
    try:
        dataset = strio.read_genemapper(
            path,
            sample_id_column=sample_id_column,
            marker_column=marker_column,
            dye_column=dye_column,
            delimiter=delimiter,
            encoding=encoding,
            require_height=require_height,
            max_height=MAX_RFU,
        )
    except strio.ParseError as error:
        raise _renderer_error(error) from error
    return _project(dataset, mode)


def _renderer_error(error: strio.ParseError) -> GeneMapperParserError:
    """Return the renderer exception that corresponds to a reader error."""

    for reader_type, renderer_type in _ERROR_TYPES:
        if isinstance(error, reader_type):
            return renderer_type(str(error))
    return GeneMapperParserError(str(error))


def _project(dataset: strio.Dataset, export_mode: str) -> GeneMapperProject:
    """Convert a reader dataset into the renderer's immutable project model."""

    samples = {sample_id: _sample(sample) for sample_id, sample in dataset.samples.items()}
    return GeneMapperProject(
        samples=samples,
        header=dataset.source.header,
        delimiter=dataset.source.delimiter,
        sample_id_column=dataset.source.sample_id_column,
        source_path=dataset.source.path,
        encoding=dataset.source.encoding,
        warnings=dataset.messages,
        export_mode=export_mode,
    )


def _sample(sample: strio.Sample) -> SampleCall:
    markers = {
        marker: MarkerCall(
            marker=locus.marker,
            dye=locus.dye,
            alleles=tuple(
                AlleleCall(
                    allele.index,
                    allele.label,
                    allele.height,
                    allele.size_bp,
                    allele.area,
                    allele.mutation,
                    allele.comment,
                )
                for allele in locus.alleles
            ),
        )
        for marker, locus in sample.loci.items()
    }
    return SampleCall(
        sample.id,
        markers,
        display_name=sample.display_name,
        sample_name=sample.sample_name,
        sample_file=sample.sample_file,
        source_sample_id=sample.source_sample_id,
        run_name=sample.run_name,
    )


__all__ = [
    "DuplicateHeaderError",
    "DuplicateMarkerError",
    "GeneMapperParserError",
    "MissingRequiredColumnError",
    "NumericConversionError",
    "read_genotypes_table",
]
