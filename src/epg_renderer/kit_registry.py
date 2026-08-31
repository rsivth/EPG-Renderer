"""Load and cache validated amplification-kit profiles bundled with the package."""

from __future__ import annotations

import json
from collections.abc import Mapping
from functools import lru_cache
from importlib.resources import files
from types import MappingProxyType

from .kit_schema import (
    DuplicateKitDefinitionError,
    KitProfile,
    KitSchemaError,
    profile_from_payload,
)
from .kits import KitDefinition, normalize_identifier
from .positions import KitCoordinateModel


def available_kit_profiles() -> tuple[KitProfile, ...]:
    """Return all bundled kit profiles in deterministic resource order."""

    return _registry()[0]


def available_kit_names() -> tuple[str, ...]:
    """Return canonical names of all bundled kits."""

    return tuple(profile.kit.name for profile in available_kit_profiles())


def available_genemapper_kit_profiles() -> tuple[KitProfile, ...]:
    """Return profiles explicitly validated for GeneMapper genotype exports."""

    return tuple(
        profile for profile in available_kit_profiles() if profile.supports_genemapper_export
    )


def available_genemapper_kit_names() -> tuple[str, ...]:
    """Return canonical names of GeneMapper-compatible kits."""

    return tuple(profile.kit.name for profile in available_genemapper_kit_profiles())


def get_kit_profile(name: str) -> KitProfile:
    """Resolve a kit profile by canonical name or alias."""

    key = normalize_identifier(name)
    try:
        return _registry()[1][key]
    except KeyError as exc:
        raise KeyError(f"Unknown kit {name!r}. Available kits: {available_kit_names()!r}.") from exc


def get_kit(name: str) -> KitDefinition:
    """Return the validated structural definition of one bundled kit."""

    return get_kit_profile(name).kit


def get_coordinate_model(name: str) -> KitCoordinateModel:
    """Return the validated nominal coordinate model of one bundled kit."""

    return get_kit_profile(name).coordinate_model


def clear_registry_cache() -> None:
    """Clear cached kit resources so tests or embedding applications can reload them."""

    _registry.cache_clear()


@lru_cache(maxsize=1)
def _registry() -> tuple[tuple[KitProfile, ...], Mapping[str, KitProfile]]:
    directory = files("epg_renderer").joinpath("data/kits")
    resources = sorted(
        (item for item in directory.iterdir() if item.name.casefold().endswith(".json")),
        key=lambda item: item.name.casefold(),
    )
    if not resources:
        raise KitSchemaError("No bundled JSON kit definitions were found.")

    profiles: list[KitProfile] = []
    aliases: dict[str, KitProfile] = {}
    for resource in resources:
        try:
            with resource.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise KitSchemaError(f"Could not read kit resource {resource.name!r}.") from exc

        profile = profile_from_payload(payload, resource_name=resource.name)
        profiles.append(profile)
        for candidate in (profile.kit.name, *profile.kit.aliases):
            key = normalize_identifier(candidate)
            existing = aliases.get(key)
            if existing is not None and existing.kit.name != profile.kit.name:
                raise DuplicateKitDefinitionError(
                    f"Kit alias {candidate!r} is shared by "
                    f"{existing.kit.name!r} and {profile.kit.name!r}."
                )
            aliases[key] = profile

    return tuple(profiles), MappingProxyType(aliases)


__all__ = [
    "DuplicateKitDefinitionError",
    "KitProfile",
    "KitSchemaError",
    "available_genemapper_kit_names",
    "available_genemapper_kit_profiles",
    "available_kit_names",
    "available_kit_profiles",
    "clear_registry_cache",
    "get_coordinate_model",
    "get_kit",
    "get_kit_profile",
    "profile_from_payload",
]
