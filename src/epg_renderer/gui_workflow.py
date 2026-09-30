"""Display-independent workflow helpers for the EPG-Renderer mini GUI."""

from __future__ import annotations

import os
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from .kit_workflow import KitMatch, KitResolutionError, detect_kits, resolve_kit
from .models import GeneMapperProject
from .parser import read_genotypes_table

_IMAGE_SUFFIXES = frozenset({".svg", ".png", ".jpg", ".jpeg"})


@dataclass(frozen=True, slots=True)
class SampleKitDecision:
    """Kit-selection state derived for one parsed sample."""

    sample_id: str
    matches: tuple[KitMatch, ...]
    compatible_kit_names: tuple[str, ...]
    resolved_kit_name: str | None
    requires_user_selection: bool


@dataclass(frozen=True, slots=True)
class FileInspection:
    """Immutable summary of a parsed input file for presentation by the GUI."""

    path: Path
    project: GeneMapperProject
    samples: tuple[SampleKitDecision, ...]

    def sample(self, sample_id: str) -> SampleKitDecision:
        """Return the selected sample or raise when the identifier is unknown."""
        for item in self.samples:
            if item.sample_id == sample_id:
                return item
        raise KeyError(sample_id)


def inspect_genemapper_file(
    path: str | Path,
    *,
    sample_id_column: str | None = None,
) -> FileInspection:
    """Parse a file and determine whether each sample has an unambiguous kit match."""

    if sample_id_column is None:
        project = read_genotypes_table(path)
    else:
        project = read_genotypes_table(path, sample_id_column=sample_id_column)
    samples = tuple(_decision_for_sample(sample_id, project) for sample_id in project.sample_ids)
    return FileInspection(Path(path), project, samples)


def suggested_output_path(
    input_path: str | Path,
    sample_id: str,
    output_format: str,
) -> Path:
    """Build the default output path for the currently selected sample."""

    source = Path(input_path)
    sample = str(sample_id).strip() or source.stem
    safe = _safe_output_stem(sample, fallback="sample")
    suffix = _output_suffix(output_format)
    return source.with_name(f"{safe}_epg{suffix}")


def default_output_directory() -> Path:
    """Return a predictable folder for images that have no input file beside them.

    The process working directory is deliberately not used: for an installed
    application it depends on how the program was started and is therefore
    unpredictable for the person using it.
    """

    home = Path.home()
    documents = home / "Documents"
    return documents if documents.is_dir() else home


def suggested_manual_output_path(
    profile_name: str,
    output_format: str,
    *,
    directory: str | Path | None = None,
    input_path: str | Path | None = None,
) -> Path:
    """Build a deterministic default output path for a manual profile.

    An explicit directory wins. Otherwise the image is proposed beside the
    currently loaded input file, and without one in the default output folder.
    """

    if directory is not None:
        base = Path(directory)
    elif input_path is not None and str(input_path).strip():
        base = Path(input_path).expanduser().parent
    else:
        base = default_output_directory()
    safe = _safe_output_stem(profile_name, fallback="manual_profile")
    return base / f"{safe}_epg{_output_suffix(output_format)}"


def choose_output_path_value(
    current_value: str,
    previous_suggestion: str | None,
    new_suggestion: str,
    *,
    force: bool = False,
) -> str:
    """Replace only an empty or still-automatic output path suggestion."""

    if force or not current_value.strip() or current_value == previous_suggestion:
        return new_suggestion
    return current_value


def validated_output_path(value: str, output_format: str) -> Path:
    """Validate and normalize a GUI output path."""

    raw = str(value).strip()
    if not raw:
        raise ValueError("Select an output file before creating the image.")
    if raw.endswith(os.sep) or (os.altsep and raw.endswith(os.altsep)):
        raise ValueError("The output path must name a file, not a directory.")
    path = Path(raw).expanduser()
    if path.exists() and path.is_dir():
        raise ValueError("The output path must name a file, not a directory.")
    return output_path_with_suffix(path, output_format)


def output_path_with_suffix(value: str | Path, output_format: str) -> Path:
    """Return a path whose suffix matches the selected output format.

    An existing image suffix is replaced. Any other dot belongs to the file name, as in
    ``run.v2`` or ``DNA-12.3``, so the format suffix is appended instead.
    """

    path = Path(value)
    suffix = _output_suffix(output_format)
    if path.suffix.casefold() in _IMAGE_SUFFIXES:
        return path.with_suffix(suffix)
    return path.with_name(path.name + suffix)


def _decision_for_sample(sample_id: str, project: GeneMapperProject) -> SampleKitDecision:
    sample = project.sample(sample_id)
    matches = detect_kits(sample, require_genemapper_compatible=True)
    compatible: list[str] = []
    for match in matches:
        try:
            resolve_kit(
                sample,
                kit_name=match.kit.name,
                require_genemapper_compatible=True,
            )
        except KitResolutionError:
            continue
        compatible.append(match.kit.name)

    resolved: str | None = None
    with suppress(KitResolutionError):
        resolved = resolve_kit(
            sample,
            require_genemapper_compatible=True,
        ).kit.name
    return SampleKitDecision(
        sample_id=sample_id,
        matches=matches,
        compatible_kit_names=tuple(compatible),
        resolved_kit_name=resolved,
        requires_user_selection=resolved is None,
    )


def _safe_output_stem(value: str, *, fallback: str) -> str:
    safe = "".join(
        character if character.isalnum() or character in "-_" else "_"
        for character in str(value).strip()
    )
    return safe.strip("_-") or fallback


def _output_suffix(output_format: str) -> str:
    normalized = str(output_format).casefold()
    if normalized == "jpeg":
        normalized = "jpg"
    if normalized not in {"svg", "png", "jpg"}:
        raise ValueError("Output format must be svg, png, jpg or jpeg.")
    return "." + normalized
