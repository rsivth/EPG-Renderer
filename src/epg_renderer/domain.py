"""Typed immutable metadata shared by kit and batch workflows."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class KitType(str, Enum):
    """Biological marker composition of an amplification kit."""

    AUTOSOMAL = "autosomal"
    Y_STR = "y_str"
    X_STR = "x_str"
    COMBINED = "combined"


class ExportCompatibility(str, Enum):
    """Analysis-software export format explicitly verified for a kit profile."""

    GENEMAPPER = "genemapper"
    GENE_MARKER = "gene_marker"
    UNKNOWN = "unknown"


class ProfileOrigin(str, Enum):
    """Origin of the allele information represented by a sample."""

    GENEMAPPER = "genemapper"
    MANUAL = "manual"


class PeakHeightMode(str, Enum):
    """Meaning of peak heights in a rendered profile."""

    RFU = "rfu"
    UNIFORM = "uniform"


class MarkerType(str, Enum):
    """Biological or technical type of a marker entry."""

    STR = "str"
    INDEL = "indel"
    AMELOGENIN = "amelogenin"
    CONTROL = "control"


class BatchStatus(str, Enum):
    """Outcome of rendering one sample in a batch operation."""

    SUCCEEDED = "ok"
    FAILED = "error"


def _required_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string.")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty.")
    return text


@dataclass(frozen=True, slots=True)
class SourceReference:
    """A source and the specific kit fact for which it was consulted."""

    title: str
    use: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "title", _required_text(self.title, "Source title"))
        object.__setattr__(self, "use", _required_text(self.use, "Source use"))


@dataclass(frozen=True, slots=True)
class MarkerMetadata:
    """Typed marker metadata beyond its ladder and dye assignment."""

    marker_type: MarkerType
    copy_group: str | None = None
    linkage_group: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.marker_type, MarkerType):
            raise TypeError("marker_type must be a MarkerType value.")
        for field_name in ("copy_group", "linkage_group"):
            value = getattr(self, field_name)
            if value is None:
                continue
            object.__setattr__(self, field_name, _required_text(value, field_name))

    @property
    def is_control(self) -> bool:
        """Return whether the marker is an internal technical control."""

        return self.marker_type is MarkerType.CONTROL


__all__ = [
    "BatchStatus",
    "ExportCompatibility",
    "KitType",
    "MarkerMetadata",
    "MarkerType",
    "PeakHeightMode",
    "ProfileOrigin",
    "SourceReference",
]
