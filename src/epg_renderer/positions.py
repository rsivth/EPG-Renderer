"""Shared coordinate types and provenance-aware peak positioning.

EPG-Renderer can use measured fragment sizes exported as ``Size n``. When size is
absent, coordinates are nominal display positions unless a kit profile explicitly states
that exact bin centres are available. Positioned peaks retain that provenance so measured,
nominal, exact and estimated coordinates cannot be mislabeled during rendering.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import Enum
from types import MappingProxyType

from .domain import PeakHeightMode, ProfileOrigin, SourceReference
from .kits import KitDefinition
from .rfu import validate_rfu


def _required_text(value: object, field_name: str) -> str:
    """Return stripped required text for a positioned value object."""

    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty.")
    return text


def _optional_text(value: object | None) -> str | None:
    """Return stripped optional text without publishing blank strings."""

    if value is None:
        return None
    return str(value).strip() or None


def _finite_decimal(value: object, field_name: str) -> Decimal:
    """Return one finite Decimal coordinate or range boundary."""

    try:
        converted = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{field_name} must be a finite decimal.") from exc
    if not converted.is_finite():
        raise ValueError(f"{field_name} must be a finite decimal.")
    return converted


class PositionModelError(ValueError):
    """Base exception for invalid coordinate models or unpositionable calls."""


class UnknownAllelePositionError(PositionModelError):
    """Raised when a called allele has no validated nominal coordinate."""


class DyeMismatchPositionError(PositionModelError):
    """Raised when the exported dye conflicts with the selected kit definition."""


class CoordinateQualityError(PositionModelError):
    """Raised when exact bin centres are required but the model is approximate."""


class CoordinateKind(str, Enum):
    """Quality and derivation category of bundled coordinates."""

    RANGE_CENTERED_NOMINAL = "range_centered_nominal"
    EXACT_BIN_CENTRES = "exact_bin_centres"


class PlacementMethod(str, Enum):
    """How one marker's allele coordinates were derived."""

    RANGE_CENTERED_REPEAT = "range_centered_repeat"
    EXPLICIT = "explicit"
    ANCHORED_REPEAT = "anchored_repeat"


class PeakCoordinateSource(str, Enum):
    """Provenance of the horizontal coordinate used for one called peak."""

    MEASURED = "measured"
    NOMINAL = "nominal"
    ESTIMATED = "estimated"
    EXACT_BIN_CENTRE = "exact_bin_centre"
    UNPOSITIONED = "unpositioned"


@dataclass(frozen=True, slots=True)
class AlleleCoordinate:
    """Nominal base-pair coordinate for one allelic-ladder allele."""

    allele: str
    nominal_bp: Decimal


@dataclass(frozen=True, slots=True)
class MarkerCoordinateDefinition:
    """Coordinate definition for one marker in one dye channel."""

    marker: str
    dye: str
    range_min_bp: Decimal
    range_max_bp: Decimal
    repeat_length_bp: int | None
    placement_method: PlacementMethod
    coordinates: tuple[AlleleCoordinate, ...]
    source_note: str

    def __post_init__(self) -> None:
        if not isinstance(self.placement_method, PlacementMethod):
            raise TypeError("placement_method must be a PlacementMethod value.")
        object.__setattr__(self, "coordinates", tuple(self.coordinates))

    def coordinate(self, allele: str) -> AlleleCoordinate:
        """Return the coordinate for one canonicalized allele label."""
        canonical = canonicalize_allele_label(allele)
        for coordinate in self.coordinates:
            if coordinate.allele == canonical:
                return coordinate
        raise UnknownAllelePositionError(
            f"No nominal coordinate for allele {allele!r} at marker {self.marker!r}."
        )

    def coordinate_or_estimate(self, allele: str) -> tuple[AlleleCoordinate, bool]:
        """Return a ladder coordinate or a bounded repeat-based estimate.

        Numeric off-ladder alleles can be displayed schematically when the marker uses
        a repeat-based coordinate model. Explicit-coordinate markers remain strict.
        """

        try:
            return self.coordinate(allele), False
        except UnknownAllelePositionError:
            if (
                self.repeat_length_bp is None
                or self.placement_method is PlacementMethod.EXPLICIT
                or not self.coordinates
            ):
                raise
        canonical = canonicalize_allele_label(allele)
        first = self.coordinates[0]
        try:
            first_code = allele_length_code(first.allele, self.repeat_length_bp)
            candidate_code = allele_length_code(canonical, self.repeat_length_bp)
        except PositionModelError as exc:
            raise UnknownAllelePositionError(
                f"No nominal coordinate for allele {allele!r} at marker {self.marker!r}."
            ) from exc
        nominal = first.nominal_bp + candidate_code - first_code
        if not self.range_min_bp <= nominal <= self.range_max_bp:
            raise UnknownAllelePositionError(
                f"Estimated coordinate for allele {allele!r} at marker {self.marker!r} "
                "lies outside the configured marker range."
            )
        return AlleleCoordinate(canonical, nominal), True

    def coordinate_map(self) -> Mapping[str, Decimal]:
        """Return a read-only mapping from allele labels to nominal base pairs."""
        return MappingProxyType(
            {coordinate.allele: coordinate.nominal_bp for coordinate in self.coordinates}
        )


@dataclass(frozen=True, slots=True)
class KitCoordinateModel:
    """Validated coordinate model for one amplification kit."""

    kit: KitDefinition = field(repr=False)
    model_version: str
    schema_version: str
    coordinate_kind: CoordinateKind
    exact_bin_centres: bool
    markers: tuple[MarkerCoordinateDefinition, ...]
    sources: tuple[SourceReference, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.kit, KitDefinition):
            raise TypeError("kit must be a KitDefinition value.")
        if not isinstance(self.coordinate_kind, CoordinateKind):
            raise TypeError("coordinate_kind must be a CoordinateKind value.")
        object.__setattr__(self, "markers", tuple(self.markers))
        object.__setattr__(self, "sources", tuple(self.sources))

    @property
    def kit_name(self) -> str:
        """Return the canonical name of the injected kit definition."""

        return self.kit.name

    def marker(self, marker: str) -> MarkerCoordinateDefinition:
        """Return the coordinate definition for a canonical or aliased marker name."""
        canonical = self.kit.canonical_marker(marker)
        if canonical is None:
            raise KeyError(marker)
        for definition in self.markers:
            if definition.marker == canonical:
                return definition
        raise KeyError(marker)

    def validate(self, kit: KitDefinition | None = None) -> None:
        """Verify consistency between this model and its kit definition."""
        selected_kit = self.kit if kit is None else kit
        if selected_kit != self.kit:
            raise PositionModelError(
                f"Coordinate model {self.kit_name!r} does not match kit {selected_kit.name!r}."
            )
        if self.exact_bin_centres != (self.coordinate_kind is CoordinateKind.EXACT_BIN_CENTRES):
            raise PositionModelError("Coordinate kind and exact-bin flag are inconsistent.")
        if self.exact_bin_centres and any(
            marker.placement_method is not PlacementMethod.EXPLICIT for marker in self.markers
        ):
            raise PositionModelError(
                "A model claiming exact bin centres must use explicit coordinates for every marker."
            )
        expected = tuple(marker.name for marker in selected_kit.markers)
        actual = tuple(marker.marker for marker in self.markers)
        if actual != expected:
            raise PositionModelError("Coordinate markers must exactly match kit marker order.")
        for coordinate, kit_marker in zip(self.markers, selected_kit.markers, strict=False):
            if coordinate.dye != kit_marker.dye:
                raise PositionModelError(f"Dye mismatch for marker {kit_marker.name!r}.")
            if coordinate.range_min_bp >= coordinate.range_max_bp:
                raise PositionModelError(f"Invalid marker range for {kit_marker.name!r}.")
            labels = tuple(item.allele for item in coordinate.coordinates)
            if labels != kit_marker.ladder_alleles:
                raise PositionModelError(
                    f"Coordinate alleles for {kit_marker.name!r} do not match the ladder."
                )
            values = tuple(item.nominal_bp for item in coordinate.coordinates)
            if values != tuple(sorted(values)) or len(values) != len(set(values)):
                raise PositionModelError(
                    f"Nominal coordinates for {kit_marker.name!r} must increase uniquely."
                )
            for item in coordinate.coordinates:
                if not (coordinate.range_min_bp <= item.nominal_bp <= coordinate.range_max_bp):
                    raise PositionModelError(
                        f"Coordinate {item.nominal_bp} for {kit_marker.name} "
                        f"{item.allele} lies outside the marker range."
                    )

    def require_exact(self) -> None:
        """Reject this model unless every coordinate is a verified exact bin centre."""
        if not self.exact_bin_centres:
            raise CoordinateQualityError(
                f"Coordinate model {self.kit_name} {self.model_version} contains nominal "
                "display coordinates, not exact GeneMapper bin centres."
            )


@dataclass(frozen=True, slots=True)
class PositioningIssue:
    """Non-fatal issue recorded when positioning in permissive mode."""

    code: str
    message: str
    marker: str
    allele: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _required_text(self.code, "code"))
        object.__setattr__(self, "message", _required_text(self.message, "message"))
        object.__setattr__(self, "marker", _required_text(self.marker, "marker"))
        object.__setattr__(self, "allele", _optional_text(self.allele))


@dataclass(frozen=True, slots=True)
class PositionedPeak:
    """One called peak enriched with a coordinate and its provenance.

    Peaks flagged as ``annotation_only`` remain marker-linked evidence but are rendered
    as marker-level badges instead of positioned peak shapes. Interpret ``coordinate_bp``
    together with ``coordinate_source``.
    """

    marker: str
    dye: str
    source_dye: str | None
    allele_index: int
    allele: str
    height: int | None
    coordinate_bp: Decimal | None
    marker_range_min_bp: Decimal
    marker_range_max_bp: Decimal
    coordinate_source: PeakCoordinateSource
    annotation_only: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.coordinate_source, PeakCoordinateSource):
            raise TypeError("coordinate_source must be a PeakCoordinateSource value.")
        if not isinstance(self.annotation_only, bool):
            raise TypeError("annotation_only must be a boolean.")
        if (
            isinstance(self.allele_index, bool)
            or not isinstance(self.allele_index, int)
            or self.allele_index < 1
        ):
            raise ValueError("allele_index must be a positive integer.")
        if self.height is not None:
            validate_rfu(self.height, allow_zero=True)

        marker = _required_text(self.marker, "marker")
        dye = _required_text(self.dye, "dye")
        allele = _required_text(self.allele, "allele")
        source_dye = _optional_text(self.source_dye)
        range_min = _finite_decimal(self.marker_range_min_bp, "marker_range_min_bp")
        range_max = _finite_decimal(self.marker_range_max_bp, "marker_range_max_bp")
        if range_min < 0:
            raise ValueError("marker_range_min_bp must not be negative.")
        if range_min >= range_max:
            raise ValueError("marker range minimum must be smaller than its maximum.")

        coordinate = self.coordinate_bp
        if coordinate is not None:
            coordinate = _finite_decimal(coordinate, "coordinate_bp")
            if self.coordinate_source is PeakCoordinateSource.UNPOSITIONED:
                raise ValueError("A peak with a coordinate cannot be marked unpositioned.")
            if not range_min <= coordinate <= range_max:
                raise ValueError("coordinate_bp must lie inside the declared marker range.")
        elif self.coordinate_source is not PeakCoordinateSource.UNPOSITIONED:
            raise ValueError("A positioned coordinate source requires coordinate_bp.")
        if self.annotation_only and self.coordinate_source is not PeakCoordinateSource.UNPOSITIONED:
            raise ValueError("An annotation-only peak must be unpositioned.")

        object.__setattr__(self, "marker", marker)
        object.__setattr__(self, "dye", dye)
        object.__setattr__(self, "source_dye", source_dye)
        object.__setattr__(self, "allele", allele)
        object.__setattr__(self, "coordinate_bp", coordinate)
        object.__setattr__(self, "marker_range_min_bp", range_min)
        object.__setattr__(self, "marker_range_max_bp", range_max)


@dataclass(frozen=True, slots=True)
class PositionedSample:
    """A sample transformed into renderer-ready, kit-ordered called peaks."""

    sample_id: str
    kit_name: str
    coordinate_model_version: str
    coordinate_kind: CoordinateKind
    exact_bin_centres: bool
    peaks: tuple[PositionedPeak, ...]
    issues: tuple[PositioningIssue, ...]
    display_name: str | None = None
    origin: ProfileOrigin = ProfileOrigin.GENEMAPPER
    height_mode: PeakHeightMode = PeakHeightMode.RFU

    def __post_init__(self) -> None:
        if not isinstance(self.coordinate_kind, CoordinateKind):
            raise TypeError("coordinate_kind must be a CoordinateKind value.")
        if not isinstance(self.exact_bin_centres, bool):
            raise TypeError("exact_bin_centres must be a boolean.")
        if not isinstance(self.origin, ProfileOrigin):
            raise TypeError("origin must be a ProfileOrigin value.")
        if not isinstance(self.height_mode, PeakHeightMode):
            raise TypeError("height_mode must be a PeakHeightMode value.")
        if self.exact_bin_centres != (self.coordinate_kind is CoordinateKind.EXACT_BIN_CENTRES):
            raise ValueError("coordinate_kind and exact_bin_centres are inconsistent.")

        sample_id = _required_text(self.sample_id, "sample_id")
        kit_name = _required_text(self.kit_name, "kit_name")
        model_version = _required_text(
            self.coordinate_model_version,
            "coordinate_model_version",
        )
        peaks = tuple(self.peaks)
        issues = tuple(self.issues)
        if any(not isinstance(peak, PositionedPeak) for peak in peaks):
            raise TypeError("peaks must contain only PositionedPeak values.")
        if any(not isinstance(issue, PositioningIssue) for issue in issues):
            raise TypeError("issues must contain only PositioningIssue values.")
        peak_keys = tuple((peak.marker, peak.allele_index) for peak in peaks)
        if len(peak_keys) != len(set(peak_keys)):
            raise ValueError("Peak allele indexes must be unique within each marker.")
        if self.height_mode is PeakHeightMode.RFU and any(peak.height is None for peak in peaks):
            raise ValueError("RFU-mode positioned peaks must contain RFU heights.")
        if self.height_mode is PeakHeightMode.UNIFORM and any(
            peak.height is not None for peak in peaks
        ):
            raise ValueError("Uniform-height positioned peaks must not contain RFU values.")

        display_name = str(self.display_name).strip() if self.display_name is not None else ""
        object.__setattr__(self, "sample_id", sample_id)
        object.__setattr__(self, "kit_name", kit_name)
        object.__setattr__(self, "coordinate_model_version", model_version)
        object.__setattr__(self, "peaks", peaks)
        object.__setattr__(self, "issues", issues)
        object.__setattr__(self, "display_name", display_name or sample_id)


def canonicalize_allele_label(value: str) -> str:
    """Normalize an allele label without converting it to floating point."""

    text = str(value).strip()
    if not text:
        raise UnknownAllelePositionError("Empty allele labels cannot be positioned.")
    upper = text.upper()
    if upper in {"X", "Y"}:
        return upper
    try:
        number = Decimal(text)
    except InvalidOperation:
        return text
    if not number.is_finite() or number < 0:
        return text
    normalized = format(number.normalize(), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized


def allele_length_code(allele: str, repeat_length_bp: int) -> Decimal:
    """Convert forensic allele nomenclature to a relative base-count code."""

    if repeat_length_bp <= 0:
        raise PositionModelError("Repeat length must be positive.")
    canonical = canonicalize_allele_label(allele)
    try:
        value = Decimal(canonical)
    except InvalidOperation as exc:
        raise PositionModelError(
            f"Allele {allele!r} is not numeric and needs an explicit coordinate."
        ) from exc
    whole = int(value)
    fraction = canonical.partition(".")[2]
    remainder = int(fraction) if fraction else 0
    if remainder >= repeat_length_bp:
        raise PositionModelError(
            f"Allele {allele!r} has a microvariant remainder incompatible with a "
            f"{repeat_length_bp}-bp repeat."
        )
    return Decimal(whole * repeat_length_bp + remainder)


__all__ = [
    "AlleleCoordinate",
    "CoordinateKind",
    "CoordinateQualityError",
    "DyeMismatchPositionError",
    "KitCoordinateModel",
    "MarkerCoordinateDefinition",
    "PeakCoordinateSource",
    "PlacementMethod",
    "PositionModelError",
    "PositionedPeak",
    "PositionedSample",
    "PositioningIssue",
    "UnknownAllelePositionError",
    "allele_length_code",
    "canonicalize_allele_label",
]
