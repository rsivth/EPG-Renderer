"""Immutable amplification-kit definitions used by the registry and renderer."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType


class KitDefinitionError(ValueError):
    """Raised when an amplification-kit definition violates an invariant."""


def normalize_identifier(value: str) -> str:
    """Normalize a kit, marker, dye, or alias for case-insensitive lookup."""

    return "".join(character for character in str(value).casefold() if character.isalnum())


def _require_identifier(value: str, field_name: str) -> str:
    text = str(value).strip()
    if not text or not normalize_identifier(text):
        raise KitDefinitionError(f"{field_name} must contain letters or digits.")
    return text


@dataclass(frozen=True, slots=True)
class DyeChannel:
    """One fluorescent dye channel in source and rendering order."""

    code: str
    label: str
    color_name: str
    order: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _require_identifier(self.code, "Dye code"))
        object.__setattr__(self, "label", _require_identifier(self.label, "Dye label"))
        object.__setattr__(
            self,
            "color_name",
            _require_identifier(self.color_name, "Dye color name"),
        )
        if self.order < 0:
            raise KitDefinitionError("Dye-channel order must be non-negative.")


@dataclass(frozen=True, slots=True)
class MarkerDefinition:
    """One marker and its allelic-ladder labels within an amplification kit."""

    name: str
    dye: str
    order_in_dye: int
    ladder_alleles: tuple[str, ...]
    aliases: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _require_identifier(self.name, "Marker name"))
        object.__setattr__(self, "dye", _require_identifier(self.dye, "Marker dye"))
        if self.order_in_dye < 0:
            raise KitDefinitionError("Marker order must be non-negative.")
        ladder = tuple(str(value).strip() for value in self.ladder_alleles)
        if not ladder or any(not value for value in ladder):
            raise KitDefinitionError(f"Marker {self.name!r} has an empty allelic ladder.")
        if len(ladder) != len(set(ladder)):
            raise KitDefinitionError(f"Marker {self.name!r} has duplicate ladder alleles.")
        aliases = tuple(_require_identifier(alias, "Marker alias") for alias in self.aliases)
        object.__setattr__(self, "ladder_alleles", ladder)
        object.__setattr__(self, "aliases", aliases)


@dataclass(frozen=True, slots=True)
class KitDefinition:
    """Validated marker and dye structure of one amplification kit."""

    name: str
    definition_version: str
    aliases: tuple[str, ...]
    channels: tuple[DyeChannel, ...]
    markers: tuple[MarkerDefinition, ...]
    _canonical_markers: Mapping[str, str] = field(init=False, repr=False, compare=False)
    _markers_by_name: Mapping[str, MarkerDefinition] = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _require_identifier(self.name, "Kit name"))
        version = str(self.definition_version).strip()
        if not version:
            raise KitDefinitionError("Kit definition_version must not be empty.")
        object.__setattr__(self, "definition_version", version)
        aliases = tuple(_require_identifier(alias, "Kit alias") for alias in self.aliases)
        channels = tuple(self.channels)
        markers = tuple(self.markers)
        object.__setattr__(self, "aliases", aliases)
        object.__setattr__(self, "channels", channels)
        object.__setattr__(self, "markers", markers)
        canonical, by_name = self._validated_indexes()
        object.__setattr__(self, "_canonical_markers", MappingProxyType(canonical))
        object.__setattr__(self, "_markers_by_name", MappingProxyType(by_name))

    def _validated_indexes(self) -> tuple[dict[str, str], dict[str, MarkerDefinition]]:
        if not self.channels:
            raise KitDefinitionError("A kit must define at least one dye channel.")
        if not self.markers:
            raise KitDefinitionError("A kit must define at least one marker.")

        channel_codes = [channel.code for channel in self.channels]
        if len(channel_codes) != len(set(channel_codes)):
            raise KitDefinitionError("Duplicate dye-channel codes.")
        if sorted(channel.order for channel in self.channels) != list(range(len(self.channels))):
            raise KitDefinitionError("Dye-channel orders must be contiguous from zero.")

        kit_namespace: set[str] = set()
        for candidate in (self.name, *self.aliases):
            key = normalize_identifier(candidate)
            if key in kit_namespace:
                raise KitDefinitionError(f"Duplicate kit name or alias {candidate!r}.")
            kit_namespace.add(key)

        marker_names = [marker.name for marker in self.markers]
        if len(marker_names) != len(set(marker_names)):
            raise KitDefinitionError("Duplicate marker names.")

        canonical: dict[str, str] = {}
        by_name: dict[str, MarkerDefinition] = {}
        known_channels = set(channel_codes)
        for marker in self.markers:
            if marker.dye not in known_channels:
                raise KitDefinitionError(
                    f"Marker {marker.name!r} references unknown dye {marker.dye!r}."
                )
            by_name[marker.name] = marker
            for candidate in (marker.name, *marker.aliases):
                key = normalize_identifier(candidate)
                previous = canonical.get(key)
                if previous is not None:
                    raise KitDefinitionError(
                        f"Marker name or alias {candidate!r} is ambiguous between "
                        f"{previous!r} and {marker.name!r}."
                    )
                canonical[key] = marker.name

        for channel in channel_codes:
            orders = [marker.order_in_dye for marker in self.markers if marker.dye == channel]
            if orders != list(range(len(orders))):
                raise KitDefinitionError(
                    f"Marker orders for dye {channel!r} must be contiguous and source-ordered."
                )
        return canonical, by_name

    def canonical_marker(self, value: str) -> str | None:
        """Return the canonical marker name for a name or alias."""

        return self._canonical_markers.get(normalize_identifier(value))

    def marker(self, value: str) -> MarkerDefinition:
        """Return one marker by canonical name or alias."""

        canonical = self.canonical_marker(value)
        if canonical is None:
            raise KeyError(value)
        return self._markers_by_name[canonical]

    @property
    def source_marker_order(self) -> tuple[str, ...]:
        """Return marker names in dye-channel and within-channel order."""

        channel_order = {channel.code: channel.order for channel in self.channels}
        ordered = sorted(
            self.markers,
            key=lambda marker: (channel_order[marker.dye], marker.order_in_dye),
        )
        return tuple(marker.name for marker in ordered)


__all__ = [
    "DyeChannel",
    "KitDefinition",
    "KitDefinitionError",
    "MarkerDefinition",
    "normalize_identifier",
]
