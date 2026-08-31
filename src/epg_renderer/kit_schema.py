"""Validation and immutable construction of declarative kit profiles."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import cast

from .domain import (
    ExportCompatibility,
    KitType,
    MarkerMetadata,
    MarkerType,
    SourceReference,
)
from .kits import DyeChannel, KitDefinition, KitDefinitionError, MarkerDefinition
from .positions import (
    AlleleCoordinate,
    CoordinateKind,
    KitCoordinateModel,
    MarkerCoordinateDefinition,
    PlacementMethod,
    allele_length_code,
    canonicalize_allele_label,
)

_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


class KitSchemaError(ValueError):
    """Raised when a JSON kit definition is malformed or internally inconsistent."""


class DuplicateKitDefinitionError(KitSchemaError):
    """Raised when kit names or aliases collide across bundled JSON resources."""


def _nonempty_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string.")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty.")
    return text


@dataclass(frozen=True, slots=True)
class KitProfile:
    """One validated kit resource and its renderer metadata."""

    kit: KitDefinition
    display_name: str
    manufacturer: str
    coordinate_model: KitCoordinateModel
    channel_colors: Mapping[str, str]
    dye_aliases: Mapping[str, str]
    sources: tuple[SourceReference, ...]
    resource_name: str
    kit_type: KitType = KitType.AUTOSOMAL
    export_compatibility: ExportCompatibility = ExportCompatibility.GENEMAPPER
    notes: tuple[str, ...] = ()
    linkage_groups: Mapping[str, tuple[str, ...]] = field(
        default_factory=lambda: MappingProxyType({})
    )
    marker_metadata: Mapping[str, MarkerMetadata] = field(
        default_factory=lambda: MappingProxyType({})
    )

    def __post_init__(self) -> None:
        if not isinstance(self.kit_type, KitType):
            raise TypeError("kit_type must be a KitType value.")
        if not isinstance(self.export_compatibility, ExportCompatibility):
            raise TypeError("export_compatibility must be an ExportCompatibility value.")
        display_name = _nonempty_text(self.display_name, "display_name")
        manufacturer = _nonempty_text(self.manufacturer, "manufacturer")
        resource_name = _nonempty_text(self.resource_name, "resource_name")
        if self.coordinate_model.kit != self.kit:
            raise ValueError("coordinate_model and kit must describe the same kit.")

        channel_colors = dict(self.channel_colors)
        expected_channels = {channel.code for channel in self.kit.channels}
        if set(channel_colors) != expected_channels:
            raise ValueError("channel_colors must define every kit channel exactly once.")
        dye_aliases = dict(self.dye_aliases)
        if any(channel not in expected_channels for channel in dye_aliases.values()):
            raise ValueError("dye_aliases contains an unknown channel code.")

        linkage_groups = {
            _nonempty_text(name, "linkage group name"): tuple(markers)
            for name, markers in self.linkage_groups.items()
        }
        marker_metadata = dict(self.marker_metadata)
        unknown_metadata = set(marker_metadata).difference(self.kit.source_marker_order)
        if unknown_metadata:
            raise ValueError(
                f"marker_metadata contains unknown markers: {sorted(unknown_metadata)!r}."
            )

        object.__setattr__(self, "display_name", display_name)
        object.__setattr__(self, "manufacturer", manufacturer)
        object.__setattr__(self, "resource_name", resource_name)
        object.__setattr__(self, "channel_colors", MappingProxyType(channel_colors))
        object.__setattr__(self, "dye_aliases", MappingProxyType(dye_aliases))
        object.__setattr__(self, "sources", tuple(self.sources))
        object.__setattr__(self, "notes", tuple(self.notes))
        object.__setattr__(self, "linkage_groups", MappingProxyType(linkage_groups))
        object.__setattr__(self, "marker_metadata", MappingProxyType(marker_metadata))

    @property
    def supports_genemapper_export(self) -> bool:
        """Return whether this profile is verified for GeneMapper exports."""

        return self.export_compatibility is ExportCompatibility.GENEMAPPER

    def normalize_dye(self, value: str) -> str | None:
        """Resolve one exported dye label to the canonical channel code."""

        return self.dye_aliases.get(_normalize_key(value))

    def channel_color(self, dye: str) -> str:
        """Return the configured SVG color for one canonical dye code."""

        try:
            return self.channel_colors[dye]
        except KeyError as exc:
            raise KeyError(f"No SVG color is defined for dye {dye!r}.") from exc


@dataclass(frozen=True, slots=True)
class _KitHeader:
    name: str
    display_name: str
    manufacturer: str
    definition_version: str
    aliases: tuple[str, ...]
    kit_type: KitType
    export_compatibility: ExportCompatibility
    notes: tuple[str, ...]
    linkage_groups: Mapping[str, tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class _ChannelData:
    channels: tuple[DyeChannel, ...]
    colors: Mapping[str, str]
    aliases: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class _MarkerData:
    markers: tuple[MarkerDefinition, ...]
    coordinates: tuple[MarkerCoordinateDefinition, ...]
    metadata: Mapping[str, MarkerMetadata]


@dataclass(frozen=True, slots=True)
class _CoordinateMetadata:
    model_version: str
    kind: CoordinateKind
    exact_bin_centres: bool


def profile_from_payload(payload: object, *, resource_name: str = "<memory>") -> KitProfile:
    """Validate a decoded kit-definition payload and build an immutable profile."""
    root = _validate_root(payload)
    schema_version = "1.1"
    kit_payload = _require_dict(root["kit"], "kit")
    header = _parse_kit_header(kit_payload)
    channel_data = _parse_channels(kit_payload)
    marker_data = _parse_markers(root)
    kit = _build_kit(header, channel_data.channels, marker_data.markers)
    linkage_groups = _canonicalize_linkage_groups(kit, header.linkage_groups)
    _validate_linkage_metadata(kit, marker_data.metadata, linkage_groups)
    coordinate_metadata = _parse_coordinate_metadata(root)
    sources = _parse_sources(root)
    _validate_resource_metadata(root)
    coordinate_model = _build_coordinate_model(
        kit,
        schema_version,
        coordinate_metadata,
        marker_data.coordinates,
        sources,
    )
    return KitProfile(
        kit=kit,
        display_name=header.display_name,
        manufacturer=header.manufacturer,
        coordinate_model=coordinate_model,
        channel_colors=channel_data.colors,
        dye_aliases=channel_data.aliases,
        sources=sources,
        resource_name=resource_name,
        kit_type=header.kit_type,
        export_compatibility=header.export_compatibility,
        notes=header.notes,
        linkage_groups=linkage_groups,
        marker_metadata=marker_data.metadata,
    )


def _validate_root(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise KitSchemaError("Kit definition root must be a JSON object.")
    if not all(isinstance(key, str) for key in payload):
        raise KitSchemaError("Kit definition root must use string object keys.")
    root = cast(dict[str, object], payload)
    schema_version = root.get("schema_version")
    if schema_version != "1.1":
        raise KitSchemaError(f"Unsupported kit schema version: {schema_version!r}; expected '1.1'.")
    _require_exact_keys(
        root,
        {"schema_version", "kit", "coordinate_model", "sources", "markers", "metadata"},
        "kit definition",
    )
    return root


def _parse_kit_header(kit_payload: dict[str, object]) -> _KitHeader:
    _require_exact_keys(
        kit_payload,
        {
            "name",
            "display_name",
            "manufacturer",
            "definition_version",
            "aliases",
            "channels",
            "kit_type",
            "export_compatibility",
            "notes",
            "linkage_groups",
        },
        "kit",
    )
    name = _identifier_string(kit_payload["name"], "kit.name")
    display_name = _nonempty_string(kit_payload["display_name"], "kit.display_name")
    manufacturer = _nonempty_string(kit_payload["manufacturer"], "kit.manufacturer")
    definition_version = _nonempty_string(
        kit_payload["definition_version"], "kit.definition_version"
    )
    aliases = _unique_identifier_tuple(kit_payload["aliases"], "kit.aliases", allow_empty=True)
    try:
        kit_type = KitType(_nonempty_string(kit_payload["kit_type"], "kit.kit_type"))
    except ValueError as exc:
        raise KitSchemaError("kit.kit_type must be autosomal, y_str, x_str or combined.") from exc
    try:
        export_compatibility = ExportCompatibility(
            _nonempty_string(kit_payload["export_compatibility"], "kit.export_compatibility")
        )
    except ValueError as exc:
        raise KitSchemaError(
            "kit.export_compatibility must be genemapper, gene_marker or unknown."
        ) from exc
    notes = _unique_string_tuple(kit_payload["notes"], "kit.notes", allow_empty=True)
    groups_payload = _require_dict(kit_payload["linkage_groups"], "kit.linkage_groups")
    linkage_groups: dict[str, tuple[str, ...]] = {}
    for group_name, group_markers in groups_payload.items():
        group = _nonempty_string(group_name, "kit.linkage_groups key")
        linkage_groups[group] = _string_tuple(
            group_markers,
            f"kit.linkage_groups[{group!r}]",
            allow_empty=False,
        )
    return _KitHeader(
        name=name,
        display_name=display_name,
        manufacturer=manufacturer,
        definition_version=definition_version,
        aliases=aliases,
        kit_type=kit_type,
        export_compatibility=export_compatibility,
        notes=notes,
        linkage_groups=MappingProxyType(linkage_groups),
    )


def _parse_channels(kit_payload: dict[str, object]) -> _ChannelData:
    channel_payloads = _require_list(kit_payload["channels"], "kit.channels", nonempty=True)
    channels: list[DyeChannel] = []
    channel_colors: dict[str, str] = {}
    dye_aliases: dict[str, str] = {}
    for index, raw in enumerate(channel_payloads):
        item = _require_dict(raw, f"kit.channels[{index}]")
        _require_exact_keys(
            item,
            {"code", "label", "color_name", "svg_color", "order", "aliases"},
            f"kit.channels[{index}]",
        )
        code = _identifier_string(item["code"], f"kit.channels[{index}].code").upper()
        label = _identifier_string(item["label"], f"kit.channels[{index}].label")
        color_name = _identifier_string(item["color_name"], f"kit.channels[{index}].color_name")
        order = _nonnegative_int(item["order"], f"kit.channels[{index}].order")
        svg_color = _nonempty_string(item["svg_color"], f"kit.channels[{index}].svg_color").upper()
        if not _HEX_COLOR.fullmatch(svg_color):
            raise KitSchemaError(f"Invalid SVG color {svg_color!r} for channel {code!r}.")
        raw_aliases = _unique_identifier_tuple(
            item["aliases"],
            f"kit.channels[{index}].aliases",
            allow_empty=False,
        )
        channels.append(DyeChannel(code, label, color_name, order))
        if code in channel_colors:
            raise KitSchemaError(f"Duplicate channel code {code!r}.")
        channel_colors[code] = svg_color
        for candidate in (code, label, color_name, *raw_aliases):
            key = _normalize_key(candidate)
            previous = dye_aliases.get(key)
            if previous is not None and previous != code:
                raise KitSchemaError(
                    f"Dye alias {candidate!r} maps to both {previous!r} and {code!r}."
                )
            dye_aliases[key] = code
    if sorted(channel.order for channel in channels) != list(range(len(channels))):
        raise KitSchemaError("Channel orders must be unique and contiguous from zero.")
    channels.sort(key=lambda item: item.order)
    return _ChannelData(
        channels=tuple(channels),
        colors=MappingProxyType(channel_colors),
        aliases=MappingProxyType(dye_aliases),
    )


def _parse_markers(root: dict[str, object]) -> _MarkerData:
    marker_payloads = _require_list(root["markers"], "markers", nonempty=True)
    markers: list[MarkerDefinition] = []
    coordinate_definitions: list[MarkerCoordinateDefinition] = []
    marker_metadata: dict[str, MarkerMetadata] = {}
    for index, raw in enumerate(marker_payloads):
        item = _require_dict(raw, f"markers[{index}]")
        marker_keys = {
            "name",
            "aliases",
            "dye",
            "order_in_dye",
            "ladder_alleles",
            "coordinate",
            "marker_type",
            "copy_group",
            "linkage_group",
            "is_control",
        }
        _require_exact_keys(item, marker_keys, f"markers[{index}]")
        marker_name = _identifier_string(item["name"], f"markers[{index}].name")
        marker_aliases = _unique_identifier_tuple(
            item["aliases"], f"markers[{index}].aliases", allow_empty=True
        )
        dye = _identifier_string(item["dye"], f"markers[{index}].dye").upper()
        order_in_dye = _nonnegative_int(item["order_in_dye"], f"markers[{index}].order_in_dye")
        ladder = _unique_allele_tuple(item["ladder_alleles"], f"markers[{index}].ladder_alleles")
        marker = MarkerDefinition(
            marker_name,
            dye,
            order_in_dye,
            ladder,
            marker_aliases,
        )
        markers.append(marker)
        coordinate_definitions.append(
            _coordinate_from_payload(
                _require_dict(item["coordinate"], f"markers[{index}].coordinate"),
                marker,
            )
        )
        marker_metadata[marker_name] = _parse_marker_metadata(item, index)
    return _MarkerData(
        markers=tuple(markers),
        coordinates=tuple(coordinate_definitions),
        metadata=MappingProxyType(marker_metadata),
    )


def _parse_marker_metadata(
    item: dict[str, object],
    index: int,
) -> MarkerMetadata:
    try:
        marker_type = MarkerType(
            _nonempty_string(item["marker_type"], f"markers[{index}].marker_type")
        )
    except ValueError as exc:
        raise KitSchemaError(
            f"markers[{index}].marker_type must be str, amelogenin, indel or control."
        ) from exc
    copy_group = _optional_nonempty_string(item["copy_group"], f"markers[{index}].copy_group")
    linkage_group = _optional_nonempty_string(
        item["linkage_group"], f"markers[{index}].linkage_group"
    )
    is_control = item["is_control"]
    if not isinstance(is_control, bool):
        raise KitSchemaError(f"markers[{index}].is_control must be boolean.")
    if is_control != (marker_type is MarkerType.CONTROL):
        raise KitSchemaError(
            f"markers[{index}].marker_type and markers[{index}].is_control are inconsistent."
        )
    return MarkerMetadata(
        marker_type=marker_type,
        copy_group=copy_group,
        linkage_group=linkage_group,
    )


def _optional_nonempty_string(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise KitSchemaError(f"{field} must be a non-empty string or null.")
    return value.strip()


def _build_kit(
    header: _KitHeader,
    channels: tuple[DyeChannel, ...],
    markers: tuple[MarkerDefinition, ...],
) -> KitDefinition:
    try:
        kit = KitDefinition(
            name=header.name,
            definition_version=header.definition_version,
            aliases=header.aliases,
            channels=channels,
            markers=markers,
        )
    except KitDefinitionError as exc:
        raise KitSchemaError(f"Invalid kit definition {header.name!r}: {exc}") from exc
    if tuple(marker.name for marker in kit.markers) != kit.source_marker_order:
        raise KitSchemaError(
            "Marker entries must be listed in channel order and order_in_dye order."
        )
    return kit


def _canonicalize_linkage_groups(
    kit: KitDefinition,
    groups: Mapping[str, tuple[str, ...]],
) -> Mapping[str, tuple[str, ...]]:
    canonical_groups: dict[str, tuple[str, ...]] = {}
    for group_name, group_markers in groups.items():
        canonical_group: list[str] = []
        for marker_name in group_markers:
            canonical = kit.canonical_marker(marker_name)
            if canonical is None:
                raise KitSchemaError(
                    f"Linkage group {group_name!r} references unknown marker {marker_name!r}."
                )
            canonical_group.append(canonical)
        if len(canonical_group) != len(set(canonical_group)):
            raise KitSchemaError(
                f"Linkage group {group_name!r} contains a duplicate canonical marker."
            )
        canonical_groups[group_name] = tuple(canonical_group)
    return MappingProxyType(canonical_groups)


def _validate_linkage_metadata(
    kit: KitDefinition,
    metadata: Mapping[str, MarkerMetadata],
    groups: Mapping[str, tuple[str, ...]],
) -> None:
    """Require marker and group linkage declarations to agree bidirectionally."""

    if not metadata:
        return
    for marker in kit.markers:
        marker_metadata = metadata[marker.name]
        declared_group = marker_metadata.linkage_group
        if declared_group is None:
            continue
        if declared_group not in groups:
            raise KitSchemaError(
                f"Marker {marker.name!r} references unknown linkage group {declared_group!r}."
            )
        if marker.name not in groups[declared_group]:
            raise KitSchemaError(
                f"Marker {marker.name!r} is not listed in declared linkage group "
                f"{declared_group!r}."
            )

    for group_name, marker_names in groups.items():
        for marker_name in marker_names:
            declared_group = metadata[marker_name].linkage_group
            if declared_group != group_name:
                raise KitSchemaError(
                    f"Linkage group {group_name!r} lists marker {marker_name!r}, "
                    "which does not declare that group."
                )


def _parse_coordinate_metadata(root: dict[str, object]) -> _CoordinateMetadata:
    model_payload = _require_dict(root["coordinate_model"], "coordinate_model")
    _require_exact_keys(
        model_payload,
        {"model_version", "coordinate_kind", "exact_bin_centres"},
        "coordinate_model",
    )
    model_version = _nonempty_string(
        model_payload["model_version"], "coordinate_model.model_version"
    )
    try:
        kind = CoordinateKind(model_payload["coordinate_kind"])
    except (TypeError, ValueError) as exc:
        raise KitSchemaError("Unknown coordinate_model.coordinate_kind.") from exc
    exact = model_payload["exact_bin_centres"]
    if not isinstance(exact, bool):
        raise KitSchemaError("coordinate_model.exact_bin_centres must be boolean.")
    return _CoordinateMetadata(model_version, kind, exact)


def _parse_sources(root: dict[str, object]) -> tuple[SourceReference, ...]:
    source_payloads = _require_list(root["sources"], "sources", nonempty=True)
    sources: list[SourceReference] = []
    for index, raw in enumerate(source_payloads):
        item = _require_dict(raw, f"sources[{index}]")
        _require_exact_keys(item, {"title", "use"}, f"sources[{index}]")
        sources.append(
            SourceReference(
                title=_nonempty_string(item["title"], f"sources[{index}].title"),
                use=_nonempty_string(item["use"], f"sources[{index}].use"),
            )
        )
    return tuple(sources)


def _validate_resource_metadata(root: dict[str, object]) -> None:
    metadata = _require_dict(root["metadata"], "metadata")
    _require_exact_keys(metadata, {"created_for", "review_status"}, "metadata")
    _nonempty_string(metadata["created_for"], "metadata.created_for")
    review_status = _nonempty_string(metadata["review_status"], "metadata.review_status")
    if review_status not in {
        "manual_transcription",
        "verified_analysis_file",
        "user_supplied",
    }:
        raise KitSchemaError("Unsupported metadata.review_status.")


def _build_coordinate_model(
    kit: KitDefinition,
    schema_version: str,
    metadata: _CoordinateMetadata,
    coordinates: tuple[MarkerCoordinateDefinition, ...],
    sources: tuple[SourceReference, ...],
) -> KitCoordinateModel:
    model = KitCoordinateModel(
        kit=kit,
        model_version=metadata.model_version,
        schema_version=schema_version,
        coordinate_kind=metadata.kind,
        exact_bin_centres=metadata.exact_bin_centres,
        markers=coordinates,
        sources=sources,
    )
    try:
        model.validate(kit)
    except ValueError as exc:
        raise KitSchemaError(f"Invalid coordinate model for {kit.name!r}: {exc}") from exc
    return model


def _coordinate_from_payload(
    payload: Mapping[str, object], marker: MarkerDefinition
) -> MarkerCoordinateDefinition:
    range_min, range_max, method, source_note, repeat = _parse_coordinate_header(payload, marker)
    if method is PlacementMethod.EXPLICIT:
        coordinates = _explicit_coordinates(payload, marker)
    elif method is PlacementMethod.RANGE_CENTERED_REPEAT:
        coordinates = _range_centered_coordinates(marker, repeat, range_min, range_max)
    elif method is PlacementMethod.ANCHORED_REPEAT:
        coordinates = _anchored_coordinates(payload, marker, repeat)
    else:  # pragma: no cover - enum exhaustiveness
        raise KitSchemaError(f"Unsupported placement method for {marker.name!r}.")

    return MarkerCoordinateDefinition(
        marker=marker.name,
        dye=marker.dye,
        range_min_bp=range_min,
        range_max_bp=range_max,
        repeat_length_bp=repeat,
        placement_method=method,
        coordinates=coordinates,
        source_note=source_note,
    )


def _parse_coordinate_header(
    payload: Mapping[str, object], marker: MarkerDefinition
) -> tuple[Decimal, Decimal, PlacementMethod, str, int | None]:
    try:
        method = PlacementMethod(str(payload.get("placement_method")))
    except ValueError as exc:
        raise KitSchemaError(f"Unknown placement method for marker {marker.name!r}.") from exc

    common = {"range_min_bp", "range_max_bp", "placement_method", "source_note"}
    method_fields = {
        PlacementMethod.EXPLICIT: {"explicit_positions"},
        PlacementMethod.RANGE_CENTERED_REPEAT: {"repeat_length_bp"},
        PlacementMethod.ANCHORED_REPEAT: {
            "repeat_length_bp",
            "anchor_allele",
            "anchor_bp",
        },
    }
    _require_exact_keys(
        payload,
        common | method_fields[method],
        f"coordinate entry for {marker.name!r} with placement method {method.value!r}",
    )

    try:
        range_min = Decimal(str(payload["range_min_bp"]))
        range_max = Decimal(str(payload["range_max_bp"]))
    except InvalidOperation as exc:
        raise KitSchemaError(f"Malformed coordinate entry for {marker.name!r}.") from exc
    if not range_min.is_finite() or not range_max.is_finite() or range_min >= range_max:
        raise KitSchemaError(f"Invalid coordinate range for {marker.name!r}.")
    source_note = _nonempty_string(payload["source_note"], f"{marker.name}.source_note")
    repeat_raw = payload.get("repeat_length_bp")
    repeat = (
        None if repeat_raw is None else _positive_int(repeat_raw, f"{marker.name}.repeat_length_bp")
    )
    return range_min, range_max, method, source_note, repeat


def _explicit_coordinates(
    payload: Mapping[str, object], marker: MarkerDefinition
) -> tuple[AlleleCoordinate, ...]:
    raw_positions = _require_dict(
        payload.get("explicit_positions"), f"{marker.name}.explicit_positions"
    )
    canonical_positions: dict[str, Decimal] = {}
    for raw_label, raw_value in raw_positions.items():
        label = canonicalize_allele_label(str(raw_label))
        if label in canonical_positions:
            raise KitSchemaError(
                f"Explicit coordinates for {marker.name!r} contain a "
                "duplicate canonical allele label."
            )
        try:
            value = Decimal(str(raw_value))
        except InvalidOperation as exc:
            raise KitSchemaError(f"Invalid explicit coordinate for {marker.name} {label}.") from exc
        if not value.is_finite():
            raise KitSchemaError(f"Non-finite explicit coordinate for {marker.name} {label}.")
        canonical_positions[label] = value
    if set(canonical_positions) != set(marker.ladder_alleles):
        raise KitSchemaError(
            f"Explicit coordinates for {marker.name!r} must exactly match ladder alleles."
        )
    return tuple(
        AlleleCoordinate(allele, canonical_positions[allele]) for allele in marker.ladder_alleles
    )


def _range_centered_coordinates(
    marker: MarkerDefinition,
    repeat: int | None,
    range_min: Decimal,
    range_max: Decimal,
) -> tuple[AlleleCoordinate, ...]:
    if repeat is None:
        raise KitSchemaError(f"Marker {marker.name!r} requires repeat_length_bp.")
    codes = [allele_length_code(allele, repeat) for allele in marker.ladder_alleles]
    span = codes[-1] - codes[0]
    available = range_max - range_min
    if available < span:
        raise KitSchemaError(f"Allelic ladder span exceeds marker range for {marker.name!r}.")
    first = range_min + (available - span) / Decimal(2)
    return tuple(
        AlleleCoordinate(allele, first + code - codes[0])
        for allele, code in zip(marker.ladder_alleles, codes, strict=False)
    )


def _anchored_coordinates(
    payload: Mapping[str, object],
    marker: MarkerDefinition,
    repeat: int | None,
) -> tuple[AlleleCoordinate, ...]:
    if repeat is None:
        raise KitSchemaError(f"Marker {marker.name!r} requires repeat_length_bp.")
    anchor_allele = canonicalize_allele_label(
        _nonempty_string(payload.get("anchor_allele"), f"{marker.name}.anchor_allele")
    )
    try:
        anchor_bp = Decimal(str(payload["anchor_bp"]))
    except (KeyError, InvalidOperation) as exc:
        raise KitSchemaError(f"Marker {marker.name!r} requires anchor_bp.") from exc
    if anchor_allele not in marker.ladder_alleles or not anchor_bp.is_finite():
        raise KitSchemaError(f"Invalid anchor for marker {marker.name!r}.")
    anchor_code = allele_length_code(anchor_allele, repeat)
    return tuple(
        AlleleCoordinate(
            allele,
            anchor_bp + allele_length_code(allele, repeat) - anchor_code,
        )
        for allele in marker.ladder_alleles
    )


def _normalize_key(value: str) -> str:
    return "".join(character for character in str(value).casefold() if character.isalnum())


def _require_dict(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise KitSchemaError(f"{field} must be an object.")
    if not all(isinstance(key, str) for key in value):
        raise KitSchemaError(f"{field} must use string object keys.")
    return cast(dict[str, object], value)


def _require_list(value: object, field: str, *, nonempty: bool) -> list[object]:
    if not isinstance(value, list) or (nonempty and not value):
        qualifier = "a non-empty list" if nonempty else "a list"
        raise KitSchemaError(f"{field} must be {qualifier}.")
    return value


def _require_exact_keys(value: Mapping[str, object], expected: set[str], field: str) -> None:
    actual = set(value)
    missing = expected - actual
    unknown = actual - expected
    if missing or unknown:
        raise KitSchemaError(
            f"{field} has missing fields {sorted(missing)} and unknown fields {sorted(unknown)}."
        )


def _nonempty_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise KitSchemaError(f"{field} must be a non-empty string.")
    return value.strip()


def _identifier_string(value: object, field: str) -> str:
    text = _nonempty_string(value, field)
    if not _normalize_key(text):
        raise KitSchemaError(f"{field} normalizes to an empty identifier.")
    return text


def _string_tuple(value: object, field: str, *, allow_empty: bool) -> tuple[str, ...]:
    items = _require_list(value, field, nonempty=not allow_empty)
    return tuple(_nonempty_string(item, f"{field}[]") for item in items)


def _unique_string_tuple(value: object, field: str, *, allow_empty: bool) -> tuple[str, ...]:
    values = _string_tuple(value, field, allow_empty=allow_empty)
    normalized = tuple(item.casefold() for item in values)
    if len(normalized) != len(set(normalized)):
        raise KitSchemaError(f"{field} contains duplicate values.")
    return values


def _unique_identifier_tuple(
    value: object,
    field: str,
    *,
    allow_empty: bool,
) -> tuple[str, ...]:
    items = _require_list(value, field, nonempty=not allow_empty)
    values = tuple(_identifier_string(item, f"{field}[]") for item in items)
    normalized = tuple(_normalize_key(item) for item in values)
    if len(normalized) != len(set(normalized)):
        raise KitSchemaError(f"{field} contains duplicate values.")
    return values


def _unique_allele_tuple(value: object, field: str) -> tuple[str, ...]:
    """Return canonical allele labels while preserving distinctions such as 4.2 vs 42."""

    items = _require_list(value, field, nonempty=True)
    values = tuple(
        canonicalize_allele_label(_nonempty_string(item, f"{field}[]")) for item in items
    )
    if len(values) != len(set(values)):
        raise KitSchemaError(f"{field} contains duplicate allele labels.")
    return values


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise KitSchemaError(f"{field} must be a non-negative integer.")
    return value


def _positive_int(value: object, field: str) -> int:
    result = _nonnegative_int(value, field)
    if result == 0:
        raise KitSchemaError(f"{field} must be positive.")
    return result
