"""Kit-agnostic detection and provenance-aware peak positioning."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from .domain import PeakHeightMode
from .kit_registry import KitProfile, available_kit_profiles, get_kit_profile
from .kits import KitDefinition
from .models import SampleCall
from .positions import (
    DyeMismatchPositionError,
    KitCoordinateModel,
    MeasuredSizeOutsideRangeError,
    PeakCoordinateSource,
    PositionedPeak,
    PositionedSample,
    PositioningIssue,
    PositionModelError,
    UnknownAllelePositionError,
    canonicalize_allele_label,
)


class Confidence(str, Enum):
    """Confidence assigned to a kit match."""

    EXACT = "exact"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NO_MATCH = "no_match"


@dataclass(frozen=True, slots=True)
class KitMatch:
    """Compatibility score between one sample and one kit definition."""

    kit: KitDefinition
    confidence: Confidence
    marker_coverage: float
    dye_agreement: float
    order_agreement: float
    missing_markers: tuple[str, ...]
    unknown_markers: tuple[str, ...]
    dye_mismatches: tuple[str, ...]
    dye_observations: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.confidence, Confidence):
            raise TypeError("confidence must be a Confidence value.")
        for name in ("marker_coverage", "dye_agreement", "order_agreement"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between zero and one.")
        object.__setattr__(self, "missing_markers", tuple(self.missing_markers))
        object.__setattr__(self, "unknown_markers", tuple(self.unknown_markers))
        object.__setattr__(self, "dye_mismatches", tuple(self.dye_mismatches))
        if (
            isinstance(self.dye_observations, bool)
            or not isinstance(self.dye_observations, int)
            or self.dye_observations < 0
        ):
            raise ValueError("dye_observations must be a non-negative integer.")


class KitResolutionError(ValueError):
    """Raised when a kit cannot be resolved safely."""


class DuplicateCanonicalMarkerError(KitResolutionError):
    """Raised when two source rows resolve to the same kit marker."""


def detect_kits(
    sample: SampleCall,
    *,
    require_genemapper_compatible: bool = False,
) -> tuple[KitMatch, ...]:
    """Rank bundled kit profiles against one sample without selecting a winner."""
    profiles = available_kit_profiles()
    if require_genemapper_compatible:
        profiles = tuple(profile for profile in profiles if profile.supports_genemapper_export)
    matches = tuple(_score_profile(sample, profile) for profile in profiles)
    return tuple(
        sorted(
            matches,
            key=lambda item: (
                _confidence_rank(item.confidence),
                item.marker_coverage,
                item.dye_agreement,
                item.order_agreement,
                item.kit.name,
            ),
            reverse=True,
        )
    )


def resolve_kit(
    sample: SampleCall,
    *,
    kit_name: str | None = None,
    minimum_confidence: Confidence = Confidence.HIGH,
    require_genemapper_compatible: bool = False,
) -> KitMatch:
    """Resolve one compatible kit profile or raise an explicit ambiguity error."""
    if kit_name is not None:
        profile = get_kit_profile(kit_name)
        _require_export_compatibility(profile, require_genemapper_compatible)
        match = _score_profile(sample, profile)
        _reject_duplicate_canonical_markers(sample, profile)
        if match.unknown_markers or match.dye_mismatches:
            details: list[str] = []
            if match.unknown_markers:
                details.append(f"unknown markers: {list(match.unknown_markers)}")
            if match.dye_mismatches:
                details.append(f"dye mismatches: {list(match.dye_mismatches)}")
            raise KitResolutionError(
                f"Explicit kit {profile.kit.name!r} is incompatible with the observed data ("
                + "; ".join(details)
                + ")."
            )
        return match

    matches = detect_kits(
        sample,
        require_genemapper_compatible=require_genemapper_compatible,
    )
    if not matches:
        qualifier = " GeneMapper-compatible" if require_genemapper_compatible else ""
        raise KitResolutionError(f"No{qualifier} JSON kit definitions are installed.")
    best = matches[0]
    profile = get_kit_profile(best.kit.name)
    _reject_duplicate_canonical_markers(sample, profile)
    if _confidence_rank(best.confidence) < _confidence_rank(minimum_confidence):
        raise KitResolutionError(
            f"Automatic kit detection is insufficient ({best.confidence.value}); "
            "provide kit_name explicitly."
        )
    if len(matches) > 1 and _same_score(matches[0], matches[1]):
        raise KitResolutionError(
            "Automatic kit detection is ambiguous; provide kit_name explicitly."
        )
    return best


def position_sample(
    sample: SampleCall,
    *,
    kit_name: str | None = None,
    model: KitCoordinateModel | None = None,
    strict: bool = True,
    require_exact_bin_centres: bool = False,
    require_genemapper_compatible: bool = False,
) -> PositionedSample:
    """Resolve a kit and map every called allele to a provenance-tagged coordinate."""
    if kit_name is None:
        match = resolve_kit(
            sample,
            require_genemapper_compatible=require_genemapper_compatible,
        )
        profile = get_kit_profile(match.kit.name)
    else:
        profile = get_kit_profile(kit_name)
        _require_export_compatibility(profile, require_genemapper_compatible)
        _reject_duplicate_canonical_markers(sample, profile)
        match = _score_profile(sample, profile)

    selected_model = model or profile.coordinate_model
    if selected_model.kit_name != profile.kit.name:
        raise PositionModelError(
            f"Coordinate model {selected_model.kit_name!r} does not match selected kit "
            f"{profile.kit.name!r}."
        )
    selected_model.validate(profile.kit)
    if require_exact_bin_centres:
        selected_model.require_exact()

    channel_order = {channel.code: channel.order for channel in match.kit.channels}
    marker_order = {
        marker.name: (channel_order[marker.dye], marker.order_in_dye)
        for marker in match.kit.markers
    }
    peaks: list[PositionedPeak] = []
    issues: list[PositioningIssue] = []
    for source_marker in sample.markers.values():
        canonical = match.kit.canonical_marker(source_marker.marker)
        if canonical is None:
            issue = PositioningIssue(
                "unknown_marker",
                f"Marker {source_marker.marker!r} is not defined for {match.kit.name}.",
                source_marker.marker,
            )
            if strict:
                raise PositionModelError(issue.message)
            issues.append(issue)
            continue
        kit_marker = match.kit.marker(canonical)
        source_dye = None if source_marker.dye is None else profile.normalize_dye(source_marker.dye)
        dye_issue: PositioningIssue | None = None
        if source_marker.dye is not None and source_dye is None:
            dye_issue = PositioningIssue(
                "unknown_dye",
                f"Marker {canonical!r} has unrecognized dye {source_marker.dye!r} "
                f"in the export; {match.kit.name} expects {kit_marker.dye!r}.",
                canonical,
            )
        elif source_dye is not None and source_dye != kit_marker.dye:
            dye_issue = PositioningIssue(
                "dye_mismatch",
                f"Marker {canonical!r} is assigned to dye {source_marker.dye!r} "
                f"in the export but to {kit_marker.dye!r} in {match.kit.name}.",
                canonical,
            )
        if dye_issue is not None:
            if strict:
                raise DyeMismatchPositionError(dye_issue.message)
            issues.append(dye_issue)
        marker_coordinates = selected_model.marker(canonical)
        for allele_call in source_marker.alleles:
            if sample.height_mode is PeakHeightMode.RFU and allele_call.height is None:
                issue = PositioningIssue(
                    "missing_height",
                    f"Marker {canonical!r} allele {allele_call.allele!r} has no exported height.",
                    canonical,
                    allele_call.allele,
                )
                if strict:
                    raise PositionModelError(issue.message)
                issues.append(issue)
                continue
            if sample.height_mode is PeakHeightMode.UNIFORM and allele_call.height is not None:
                raise PositionModelError(
                    "Uniform-height samples must not contain numerical RFU values."
                )
            annotation_only = False
            try:
                if allele_call.size_bp is not None:
                    if not (
                        marker_coordinates.range_min_bp
                        <= allele_call.size_bp
                        <= marker_coordinates.range_max_bp
                    ):
                        raise MeasuredSizeOutsideRangeError(
                            f"Marker {canonical!r} allele {allele_call.allele!r} has measured "
                            f"size {allele_call.size_bp} bp outside the marker range "
                            f"{marker_coordinates.range_min_bp}–"
                            f"{marker_coordinates.range_max_bp} bp of {match.kit.name}."
                        )
                    coordinate_bp = allele_call.size_bp
                    coordinate_source = PeakCoordinateSource.MEASURED
                    allele_label = canonicalize_allele_label(allele_call.allele)
                    estimated = False
                else:
                    coordinate, estimated = marker_coordinates.coordinate_or_estimate(
                        allele_call.allele
                    )
                    coordinate_bp = coordinate.nominal_bp
                    allele_label = coordinate.allele
                    if estimated:
                        coordinate_source = PeakCoordinateSource.ESTIMATED
                    elif selected_model.exact_bin_centres:
                        coordinate_source = PeakCoordinateSource.EXACT_BIN_CENTRE
                    else:
                        coordinate_source = PeakCoordinateSource.NOMINAL
                if estimated:
                    issues.append(
                        PositioningIssue(
                            "estimated_allele_coordinate",
                            f"Marker {canonical!r} allele {allele_call.allele!r} uses a "
                            "repeat-based nominal coordinate outside the bundled ladder.",
                            canonical,
                            allele_call.allele,
                        )
                    )
            except MeasuredSizeOutsideRangeError as exc:
                if strict:
                    raise
                issues.append(
                    PositioningIssue(
                        "measured_size_outside_range",
                        str(exc),
                        canonical,
                        allele_call.allele,
                    )
                )
                allele_label = canonicalize_allele_label(allele_call.allele)
                coordinate_bp = None
                coordinate_source = PeakCoordinateSource.UNPOSITIONED
            except UnknownAllelePositionError as exc:
                allele_label = canonicalize_allele_label(allele_call.allele)
                issue_code = "unknown_allele"
                issue_message = str(exc)
                if allele_call.size_bp is None and allele_label.casefold() == "ol":
                    issue_code = "off_ladder_without_size"
                    issue_message = (
                        f"Marker {canonical!r} contains off-ladder allele {allele_call.allele!r} "
                        "without exported size information; the EPG will show a marker-level "
                        "OL annotation instead of a positioned peak."
                    )
                    annotation_only = True
                issue = PositioningIssue(issue_code, issue_message, canonical, allele_call.allele)
                if strict and not annotation_only:
                    raise
                issues.append(issue)
                coordinate_bp = None
                coordinate_source = PeakCoordinateSource.UNPOSITIONED
            peaks.append(
                PositionedPeak(
                    marker=canonical,
                    dye=kit_marker.dye,
                    source_dye=source_marker.dye,
                    allele_index=allele_call.allele_index,
                    allele=allele_label,
                    height=allele_call.height,
                    coordinate_bp=coordinate_bp,
                    marker_range_min_bp=marker_coordinates.range_min_bp,
                    marker_range_max_bp=marker_coordinates.range_max_bp,
                    annotation_only=annotation_only,
                    coordinate_source=coordinate_source,
                )
            )
    peaks.sort(
        key=lambda peak: (
            *marker_order[peak.marker],
            peak.coordinate_bp is None,
            peak.coordinate_bp if peak.coordinate_bp is not None else Decimal("Infinity"),
            peak.allele_index,
        )
    )
    return PositionedSample(
        sample_id=sample.sample_id,
        kit_name=match.kit.name,
        coordinate_model_version=selected_model.model_version,
        coordinate_kind=selected_model.coordinate_kind,
        exact_bin_centres=selected_model.exact_bin_centres,
        peaks=tuple(peaks),
        issues=tuple(issues),
        display_name=sample.display_name,
        origin=sample.origin,
        height_mode=sample.height_mode,
    )


def _require_export_compatibility(
    profile: KitProfile,
    required: bool,
) -> None:
    if required and not profile.supports_genemapper_export:
        raise KitResolutionError(
            f"Kit {profile.kit.name!r} is not enabled for GeneMapper exports "
            f"(declared compatibility: {profile.export_compatibility.value!r})."
        )


def _reject_duplicate_canonical_markers(
    sample: SampleCall,
    profile: KitProfile,
) -> None:
    observed: dict[str, str] = {}
    for marker_call in sample.markers.values():
        canonical = profile.kit.canonical_marker(marker_call.marker)
        if canonical is None:
            continue
        previous = observed.get(canonical)
        if previous is not None:
            raise DuplicateCanonicalMarkerError(
                f"Marker rows {previous!r} and {marker_call.marker!r} both resolve "
                f"to canonical marker {canonical!r} for kit {profile.kit.name!r}."
            )
        observed[canonical] = marker_call.marker


def _score_profile(sample: SampleCall, profile: KitProfile) -> KitMatch:
    kit = profile.kit
    expected = kit.source_marker_order
    expected_set = set(expected)
    observed: list[str] = []
    unknown: list[str] = []
    mismatches: list[str] = []
    dye_observations = 0
    for marker_call in sample.markers.values():
        canonical = kit.canonical_marker(marker_call.marker)
        if canonical is None:
            unknown.append(marker_call.marker)
            continue
        observed.append(canonical)
        if marker_call.dye is not None:
            dye_observations += 1
            if profile.normalize_dye(marker_call.dye) != kit.marker(canonical).dye:
                mismatches.append(canonical)
    observed_set = set(observed)
    missing = tuple(marker for marker in expected if marker not in observed_set)
    coverage = len(observed_set) / len(expected_set) if expected_set else 0.0
    dye_agreement = (
        (dye_observations - len(mismatches)) / dye_observations if dye_observations else 1.0
    )
    order_agreement = _relative_order_agreement(observed, expected)
    complete_dye_evidence = dye_observations == len(observed) and bool(observed)
    if (
        coverage == 1.0
        and not unknown
        and complete_dye_evidence
        and dye_agreement == 1.0
        and order_agreement == 1.0
    ):
        confidence = Confidence.EXACT
    elif coverage >= 0.90 and dye_agreement == 1.0 and not unknown and order_agreement >= 0.90:
        confidence = Confidence.HIGH
    elif coverage >= 0.70 and dye_agreement >= 0.90 and order_agreement >= 0.70:
        confidence = Confidence.MEDIUM
    elif coverage >= 0.20 and dye_agreement >= 0.75 and order_agreement >= 0.50:
        confidence = Confidence.LOW
    else:
        confidence = Confidence.NO_MATCH
    return KitMatch(
        kit=kit,
        confidence=confidence,
        marker_coverage=coverage,
        dye_agreement=dye_agreement,
        order_agreement=order_agreement,
        missing_markers=missing,
        unknown_markers=tuple(unknown),
        dye_mismatches=tuple(mismatches),
        dye_observations=dye_observations,
    )


def _relative_order_agreement(observed: Iterable[str], expected: tuple[str, ...]) -> float:
    values = list(observed)
    if len(values) < 2:
        return 1.0 if values else 0.0
    position = {marker: index for index, marker in enumerate(expected)}
    comparable = [marker for marker in values if marker in position]
    total = 0
    correct = 0
    for left_index in range(len(comparable)):
        for right_index in range(left_index + 1, len(comparable)):
            total += 1
            if position[comparable[left_index]] < position[comparable[right_index]]:
                correct += 1
    return correct / total if total else 1.0


def _confidence_rank(value: Confidence) -> int:
    return {
        Confidence.NO_MATCH: 0,
        Confidence.LOW: 1,
        Confidence.MEDIUM: 2,
        Confidence.HIGH: 3,
        Confidence.EXACT: 4,
    }[value]


def _same_score(left: KitMatch, right: KitMatch) -> bool:
    return (
        left.confidence == right.confidence
        and left.marker_coverage == right.marker_coverage
        and left.dye_agreement == right.dye_agreement
        and left.order_agreement == right.order_agreement
    )


__all__ = [
    "Confidence",
    "DuplicateCanonicalMarkerError",
    "KitMatch",
    "KitResolutionError",
    "detect_kits",
    "position_sample",
    "resolve_kit",
]
