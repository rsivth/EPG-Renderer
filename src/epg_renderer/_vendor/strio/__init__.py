"""STRio -- read forensic STR typing results into one format-neutral data model.

Quick start::

    import strio

    dataset = strio.read_genemapper("export.txt")
    for sample in dataset.samples.values():
        for locus in sample.loci.values():
            print(sample.id, locus.marker, locus.labels)

See ``docs/MANUAL.md`` for the full guide.
"""

from .alleles import AlleleKind, AlleleValue, parse_allele_label
from .diagnostics import Diagnostic, DiagnosticCode
from .errors import (
    DuplicateColumnError,
    DuplicateLocusError,
    InconsistentExtraError,
    MissingColumnError,
    NumericValueError,
    ParseError,
    StrioError,
)
from .formats.genemapper import parse_genemapper, read_genemapper
from .markers import MARKER_SYNONYMS, marker_key
from .model import Allele, Dataset, Locus, Sample, SourceInfo
from .version import __version__

__all__ = [
    "MARKER_SYNONYMS",
    "Allele",
    "AlleleKind",
    "AlleleValue",
    "Dataset",
    "Diagnostic",
    "DiagnosticCode",
    "DuplicateColumnError",
    "DuplicateLocusError",
    "InconsistentExtraError",
    "Locus",
    "MissingColumnError",
    "NumericValueError",
    "ParseError",
    "Sample",
    "SourceInfo",
    "StrioError",
    "__version__",
    "marker_key",
    "parse_allele_label",
    "parse_genemapper",
    "read_genemapper",
]
