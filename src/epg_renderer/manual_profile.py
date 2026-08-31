"""Validated construction of schematic profiles entered manually by a user."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from .domain import PeakHeightMode, ProfileOrigin
from .kit_registry import get_kit_profile
from .models import AlleleCall, MarkerCall, SampleCall
from .positions import UnknownAllelePositionError, canonicalize_allele_label
from .rfu import validate_rfu

_VALUE_SEPARATOR = re.compile(r"[\s,;]+")


class ManualProfileError(ValueError):
    """Raised when a manually entered profile is incomplete or inconsistent."""


@dataclass(frozen=True, slots=True)
class ManualMarkerEntry:
    """Validated manually entered alleles and optional RFU heights for one marker."""

    marker: str
    alleles: tuple[str, ...]
    heights: tuple[int, ...] | None

    def __post_init__(self) -> None:
        marker = str(self.marker).strip()
        if not marker:
            raise ManualProfileError("Marker name must not be empty.")
        alleles = tuple(str(value).strip() for value in self.alleles)
        if not alleles or any(not value for value in alleles):
            raise ManualProfileError(f"Marker {marker!r} must contain at least one allele.")
        heights = None if self.heights is None else tuple(self.heights)
        if heights is not None:
            if len(heights) != len(alleles):
                raise ManualProfileError(
                    f"Marker {marker}: enter exactly one RFU height for each allele."
                )
            heights = tuple(_validate_manual_rfu(marker, value) for value in heights)
        object.__setattr__(self, "marker", marker)
        object.__setattr__(self, "alleles", alleles)
        object.__setattr__(self, "heights", heights)


@dataclass(frozen=True, slots=True)
class ManualProfile:
    """One validated manual profile ready for positioning and rendering."""

    name: str
    kit_name: str
    height_mode: PeakHeightMode
    markers: tuple[ManualMarkerEntry, ...]

    def __post_init__(self) -> None:
        name = str(self.name).strip()
        if not name:
            raise ManualProfileError("Enter a profile name.")
        if not isinstance(self.height_mode, PeakHeightMode):
            raise TypeError("height_mode must be a PeakHeightMode value.")
        kit_name = str(self.kit_name).strip()
        if not kit_name:
            raise ManualProfileError("Select an amplification kit.")
        markers = tuple(self.markers)
        if not markers:
            raise ManualProfileError("Enter at least one allele before using the profile.")
        if any(not isinstance(entry, ManualMarkerEntry) for entry in markers):
            raise TypeError("markers must contain only ManualMarkerEntry values.")
        marker_names = tuple(entry.marker for entry in markers)
        if len(marker_names) != len(set(marker_names)):
            raise ManualProfileError("Each marker may occur only once in a manual profile.")
        for entry in markers:
            _validate_height_mode(entry, self.height_mode)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "kit_name", kit_name)
        object.__setattr__(self, "markers", markers)

    def to_sample_call(self) -> SampleCall:
        """Convert the validated manual profile into the shared sample data model."""

        marker_calls: dict[str, MarkerCall] = {}
        profile = get_kit_profile(self.kit_name)
        for entry in self.markers:
            marker_definition = profile.kit.marker(entry.marker)
            calls = tuple(
                AlleleCall(
                    allele_index=index,
                    allele=allele,
                    height=None if entry.heights is None else entry.heights[index - 1],
                )
                for index, allele in enumerate(entry.alleles, start=1)
            )
            marker_calls[entry.marker] = MarkerCall(
                marker=entry.marker,
                dye=marker_definition.dye,
                alleles=calls,
            )
        return SampleCall(
            sample_id=self.name,
            display_name=self.name,
            sample_name=self.name,
            markers=marker_calls,
            origin=ProfileOrigin.MANUAL,
            height_mode=self.height_mode,
        )


def editable_marker_names(kit_name: str) -> tuple[str, ...]:
    """Return biological kit markers that may receive manual allele entries."""

    profile = get_kit_profile(kit_name)
    return tuple(
        marker.name
        for marker in profile.kit.markers
        if not profile.marker_metadata[marker.name].is_control
    )


def parse_manual_marker_text(
    marker: str,
    allele_text: str,
    height_text: str,
    height_mode: PeakHeightMode | str,
) -> ManualMarkerEntry | None:
    """Parse comma-, semicolon-, or whitespace-separated values from one GUI row."""

    try:
        mode = PeakHeightMode(height_mode)
    except ValueError as exc:
        raise ManualProfileError(f"Unknown peak-height mode: {height_mode!r}.") from exc
    alleles = _split_values(allele_text)
    heights_raw = _split_values(height_text)
    if not alleles and not heights_raw:
        return None
    if not alleles:
        raise ManualProfileError(f"Marker {marker}: RFU heights were entered without alleles.")
    if mode is PeakHeightMode.UNIFORM:
        if heights_raw:
            raise ManualProfileError(
                f"Marker {marker}: remove RFU values or select the RFU-height mode."
            )
        return ManualMarkerEntry(marker, alleles, None)
    if len(heights_raw) != len(alleles):
        raise ManualProfileError(
            f"Marker {marker}: enter exactly one positive RFU height for each allele."
        )
    heights: list[int] = []
    for raw in heights_raw:
        try:
            value = int(raw)
        except ValueError as exc:
            raise ManualProfileError(
                f"Marker {marker}: RFU height {raw!r} is not a whole number."
            ) from exc
        heights.append(_validate_manual_rfu(marker, value))
    return ManualMarkerEntry(marker, alleles, tuple(heights))


def build_manual_profile(
    name: str,
    kit_name: str,
    entries: Mapping[str, ManualMarkerEntry],
    *,
    height_mode: PeakHeightMode | str,
) -> ManualProfile:
    """Validate manual marker entries against one bundled kit definition."""

    try:
        mode = PeakHeightMode(height_mode)
    except ValueError as exc:
        raise ManualProfileError(f"Unknown peak-height mode: {height_mode!r}.") from exc
    try:
        profile = get_kit_profile(kit_name)
    except KeyError as exc:
        raise ManualProfileError(str(exc)) from exc

    editable = set(editable_marker_names(profile.kit.name))
    unknown = tuple(sorted(set(entries) - editable))
    if unknown:
        raise ManualProfileError(
            f"Manual entries contain unsupported or technical-control markers: {unknown!r}."
        )

    validated: list[ManualMarkerEntry] = []
    for marker in profile.kit.source_marker_order:
        entry = entries.get(marker)
        if entry is None:
            continue
        if entry.marker != marker:
            raise ManualProfileError(
                f"Marker mapping key {marker!r} does not match entry {entry.marker!r}."
            )
        _validate_height_mode(entry, mode)
        canonical_alleles = tuple(canonicalize_allele_label(value) for value in entry.alleles)
        if len(set(canonical_alleles)) != len(canonical_alleles):
            raise ManualProfileError(f"Marker {marker}: duplicate allele entries are not allowed.")
        coordinates = profile.coordinate_model.marker(marker)
        for allele in canonical_alleles:
            try:
                coordinates.coordinate_or_estimate(allele)
            except UnknownAllelePositionError as exc:
                raise ManualProfileError(
                    f"Marker {marker}: allele {allele!r} cannot be positioned for this kit."
                ) from exc
        validated.append(ManualMarkerEntry(marker, canonical_alleles, entry.heights))

    if not validated:
        raise ManualProfileError("Enter at least one allele before using the profile.")
    return ManualProfile(
        name=name,
        kit_name=profile.kit.name,
        height_mode=mode,
        markers=tuple(validated),
    )


def _validate_height_mode(entry: ManualMarkerEntry, mode: PeakHeightMode) -> None:
    if mode is PeakHeightMode.UNIFORM:
        if entry.heights is not None:
            raise ManualProfileError(
                f"Marker {entry.marker}: uniform-height profiles must not contain RFU values."
            )
        return
    if entry.heights is None or len(entry.heights) != len(entry.alleles):
        raise ManualProfileError(
            f"Marker {entry.marker}: enter exactly one RFU height for each allele."
        )


def _validate_manual_rfu(marker: str, value: object) -> int:
    try:
        return validate_rfu(value, allow_zero=False)
    except ValueError as exc:
        raise ManualProfileError(f"Marker {marker}: {exc}") from exc


def _split_values(value: str) -> tuple[str, ...]:
    text = str(value).strip()
    if not text:
        return ()
    return tuple(item for item in _VALUE_SEPARATOR.split(text) if item)


__all__ = [
    "ManualMarkerEntry",
    "ManualProfile",
    "ManualProfileError",
    "build_manual_profile",
    "editable_marker_names",
    "parse_manual_marker_text",
]
