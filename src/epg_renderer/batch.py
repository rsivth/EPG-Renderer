"""Batch rendering and manifest generation for GeneMapper genotype exports.

The public entry point validates one request and delegates stateful processing to a
single runner. Expected sample-level failures remain isolated, while unexpected defects
are recorded in the manifest and re-raised.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath

from .domain import BatchStatus
from .kit_registry import get_kit_profile
from .kit_workflow import KitResolutionError, resolve_kit
from .models import GeneMapperProject, SampleCall
from .parser import GeneMapperParserError, read_genotypes_table
from .positions import PositionModelError
from .render_document import render_sample_svg
from .render_io import _atomic_write_text, write_epg_output
from .render_options import (
    OutputFormat,
    RasterRenderOptions,
    SampleSelectionError,
    SvgRenderError,
    SvgRenderOptions,
)
from .version import __version__

_EXPECTED_SAMPLE_ERRORS = (KitResolutionError, PositionModelError, SvgRenderError)
_BATCH_OUTPUT_SUFFIXES = frozenset({".svg", ".png", ".jpg", ".jpeg"})


@dataclass(frozen=True, slots=True)
class BatchRenderItem:
    """Outcome for one sample in a batch-render operation."""

    sample_id: str
    output_path: Path | None
    status: BatchStatus
    error: str | None = None

    def __post_init__(self) -> None:
        sample_id = str(self.sample_id).strip()
        if not sample_id:
            raise ValueError("sample_id must not be empty.")
        if not isinstance(self.status, BatchStatus):
            raise TypeError("status must be a BatchStatus value.")
        object.__setattr__(self, "sample_id", sample_id)
        output_path = None if self.output_path is None else Path(self.output_path)
        error = None if self.error is None else str(self.error).strip() or None
        if self.status is BatchStatus.SUCCEEDED:
            if output_path is None:
                raise ValueError("A successful batch item requires output_path.")
            if error is not None:
                raise ValueError("A successful batch item must not contain an error.")
        else:
            if output_path is not None:
                raise ValueError("A failed batch item must not contain output_path.")
            if error is None:
                raise ValueError("A failed batch item requires an error message.")
        object.__setattr__(self, "output_path", output_path)
        object.__setattr__(self, "error", error)


@dataclass(frozen=True, slots=True)
class BatchRenderResult:
    """Summary returned after rendering every sample in one export."""

    input_path: Path
    output_dir: Path
    kit_name: str | None
    output_format: OutputFormat
    items: tuple[BatchRenderItem, ...]
    manifest_path: Path

    def __post_init__(self) -> None:
        if not isinstance(self.output_format, OutputFormat):
            raise TypeError("output_format must be an OutputFormat value.")
        kit_name = None if self.kit_name is None else str(self.kit_name).strip()
        if self.kit_name is not None and not kit_name:
            raise ValueError("kit_name must be non-empty or None.")
        items = tuple(self.items)
        if any(not isinstance(item, BatchRenderItem) for item in items):
            raise TypeError("items must contain only BatchRenderItem values.")
        sample_ids = tuple(item.sample_id for item in items)
        if len(sample_ids) != len(set(sample_ids)):
            raise ValueError("Batch result sample identifiers must be unique.")
        object.__setattr__(self, "input_path", Path(self.input_path))
        object.__setattr__(self, "output_dir", Path(self.output_dir))
        object.__setattr__(self, "kit_name", kit_name)
        object.__setattr__(self, "items", items)
        object.__setattr__(self, "manifest_path", Path(self.manifest_path))

    @property
    def succeeded(self) -> int:
        """Return the number of successfully rendered samples."""

        return sum(item.status is BatchStatus.SUCCEEDED for item in self.items)

    @property
    def failed(self) -> int:
        """Return the number of failed samples."""

        return sum(item.status is BatchStatus.FAILED for item in self.items)


@dataclass(frozen=True, slots=True)
class _BatchRequest:
    """Validated immutable inputs for one batch-render operation."""

    input_path: Path
    output_dir: Path
    output_format: OutputFormat
    kit_name: str | None
    options: SvgRenderOptions | None
    raster_options: RasterRenderOptions | None
    strict_positioning: bool
    sample_id_column: str | None
    continue_on_error: bool

    @property
    def manifest_path(self) -> Path:
        """Return the path of the JSON manifest for the current batch."""
        return self.output_dir / "epg_batch_manifest.json"

    @property
    def output_suffix(self) -> str:
        """Return the canonical filename suffix for the selected output format."""
        return ".jpg" if self.output_format is OutputFormat.JPEG else f".{self.output_format.value}"


@dataclass(slots=True)
class _BatchRunner:
    """Own mutable state for one batch without leaking it into the public API."""

    request: _BatchRequest
    items: list[BatchRenderItem] = field(default_factory=list)
    used_names: set[str] = field(default_factory=set)
    resolved_kit: str | None = None

    def run(self) -> BatchRenderResult:
        """Execute the batch request and return the immutable result summary."""
        self._retire_previous_outputs()
        project = self._load_project()
        self._require_samples(project)
        self._resolve_requested_kit()
        for sample_id in project.sample_ids:
            self._render_one_sample(project.sample(sample_id))
        self._write_manifest()
        return self._result()

    def _retire_previous_outputs(self) -> None:
        """Remove only outputs owned by the previous valid batch manifest."""

        manifest_path = self.request.manifest_path
        if not manifest_path.exists():
            return
        for path in _previous_batch_output_paths(manifest_path, self.request.output_dir):
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                raise SvgRenderError(
                    f"Could not retire previous batch output {path}: {exc}"
                ) from exc

    def _load_project(self) -> GeneMapperProject:
        try:
            if self.request.sample_id_column is None:
                return read_genotypes_table(self.request.input_path)
            return read_genotypes_table(
                self.request.input_path,
                sample_id_column=self.request.sample_id_column,
            )
        except GeneMapperParserError as exc:
            self._write_manifest(batch_error=exc)
            raise

    def _require_samples(self, project: GeneMapperProject) -> None:
        if project.sample_ids:
            return
        error = SampleSelectionError("The GeneMapper export contains no samples.")
        self._write_manifest(batch_error=error)
        raise error

    def _resolve_requested_kit(self) -> None:
        if self.request.kit_name is None:
            return
        try:
            profile = get_kit_profile(self.request.kit_name)
        except KeyError as exc:
            error = KitResolutionError(str(exc))
            self._write_manifest(batch_error=error, manifest_kit_name=str(self.request.kit_name))
            raise error from exc
        if not profile.supports_genemapper_export:
            error = KitResolutionError(
                f"Kit {profile.kit.name!r} is not enabled for GeneMapper exports "
                f"(declared compatibility: {profile.export_compatibility.value!r})."
            )
            self._write_manifest(batch_error=error, manifest_kit_name=profile.kit.name)
            raise error
        self.resolved_kit = profile.kit.name

    def _render_one_sample(self, sample: SampleCall) -> None:
        """Render one sample at the batch system boundary and record its outcome."""

        path = self._next_output_path(sample.sample_id)
        try:
            self._render_sample(sample, path)
        except _EXPECTED_SAMPLE_ERRORS as exc:
            self.items.append(_failed_item(sample.sample_id, exc))
            if not self.request.continue_on_error:
                self._write_manifest()
                raise
        except Exception as exc:
            self.items.append(_failed_item(sample.sample_id, exc, unexpected=True))
            self._write_manifest(batch_error=exc)
            raise
        else:
            self.items.append(BatchRenderItem(sample.sample_id, path, BatchStatus.SUCCEEDED))

    def _render_sample(self, sample: SampleCall, path: Path) -> None:
        match = resolve_kit(
            sample,
            kit_name=self.resolved_kit if self.request.kit_name is not None else None,
            require_genemapper_compatible=True,
        )
        self._accept_common_kit(match.kit.name)
        svg = render_sample_svg(
            sample,
            kit_name=self.resolved_kit,
            options=self.request.options,
            strict_positioning=self.request.strict_positioning,
            require_genemapper_compatible=True,
        )
        write_epg_output(svg, path, raster_options=self.request.raster_options)

    def _accept_common_kit(self, detected_kit: str) -> None:
        if self.resolved_kit is None:
            self.resolved_kit = detected_kit
            return
        if detected_kit != self.resolved_kit:
            raise SvgRenderError(
                "Batch rendering requires one common kit for all samples; "
                f"encountered {self.resolved_kit!r} and {detected_kit!r}. "
                "Supply --kit explicitly if appropriate."
            )

    def _next_output_path(self, sample_id: str) -> Path:
        stem = safe_output_stem(sample_id)
        candidate = stem
        counter = 2
        while candidate.casefold() in self.used_names:
            candidate = f"{stem}_{counter}"
            counter += 1
        self.used_names.add(candidate.casefold())
        return self.request.output_dir / f"{candidate}{self.request.output_suffix}"

    def _write_manifest(
        self,
        *,
        batch_error: Exception | None = None,
        manifest_kit_name: str | None = None,
    ) -> None:
        _write_batch_manifest(
            self.request.manifest_path,
            input_path=self.request.input_path,
            kit_name=self.resolved_kit if manifest_kit_name is None else manifest_kit_name,
            output_format=self.request.output_format,
            items=self.items,
            batch_error=batch_error,
        )

    def _result(self) -> BatchRenderResult:
        return BatchRenderResult(
            input_path=self.request.input_path,
            output_dir=self.request.output_dir,
            kit_name=self.resolved_kit,
            output_format=self.request.output_format,
            items=tuple(self.items),
            manifest_path=self.request.manifest_path,
        )


def render_genemapper_batch(
    input_path: str | Path,
    output_dir: str | Path,
    *,
    output_format: OutputFormat | str = OutputFormat.SVG,
    kit_name: str | None = None,
    options: SvgRenderOptions | None = None,
    raster_options: RasterRenderOptions | None = None,
    strict_positioning: bool = True,
    sample_id_column: str | None = None,
    continue_on_error: bool = True,
) -> BatchRenderResult:
    """Render every sample while isolating expected per-sample failures."""

    request = _BatchRequest(
        input_path=Path(input_path),
        output_dir=Path(output_dir),
        output_format=_parse_output_format(output_format),
        kit_name=kit_name,
        options=options,
        raster_options=raster_options,
        strict_positioning=strict_positioning,
        sample_id_column=sample_id_column,
        continue_on_error=continue_on_error,
    )
    request.output_dir.mkdir(parents=True, exist_ok=True)
    return _BatchRunner(request).run()


def _parse_output_format(value: OutputFormat | str) -> OutputFormat:
    try:
        return value if isinstance(value, OutputFormat) else OutputFormat(str(value).casefold())
    except ValueError as exc:
        raise SvgRenderError("output_format must be svg, png or jpeg.") from exc


def _previous_batch_output_paths(manifest_path: Path, output_dir: Path) -> tuple[Path, ...]:
    """Return validated output paths recorded by a previous batch manifest."""

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("the top-level value must be an object")
        items = manifest.get("items")
        if not isinstance(items, list):
            raise ValueError("the 'items' field must be an array")

        paths: list[Path] = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError(f"item {index} must be an object")
            output_file = item.get("output_file")
            if output_file is None:
                continue
            if not isinstance(output_file, str):
                raise ValueError(f"item {index} has a non-text output filename")
            paths.append(_validated_previous_output_path(output_dir, output_file))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise SvgRenderError(f"Could not use the previous batch manifest safely: {exc}") from exc
    return tuple(dict.fromkeys(paths))


def _validated_previous_output_path(output_dir: Path, output_file: str) -> Path:
    """Resolve one manifest filename without accepting paths on any supported OS."""

    posix_path = PurePosixPath(output_file)
    windows_path = PureWindowsPath(output_file)
    if (
        not output_file
        or posix_path.is_absolute()
        or windows_path.is_absolute()
        or len(posix_path.parts) != 1
        or len(windows_path.parts) != 1
        or posix_path.suffix.casefold() not in _BATCH_OUTPUT_SUFFIXES
    ):
        raise ValueError(f"unsafe output filename {output_file!r}")
    return output_dir / output_file


def _failed_item(
    sample_id: str,
    error: Exception,
    *,
    unexpected: bool = False,
) -> BatchRenderItem:
    prefix = "Unexpected " if unexpected else ""
    return BatchRenderItem(
        sample_id,
        None,
        BatchStatus.FAILED,
        f"{prefix}{type(error).__name__}: {error}",
    )


def _write_batch_manifest(
    manifest_path: Path,
    *,
    input_path: Path,
    kit_name: str | None,
    output_format: OutputFormat,
    items: Sequence[BatchRenderItem],
    batch_error: Exception | None = None,
) -> None:
    manifest = {
        "epg_renderer_version": __version__,
        "input_path": str(input_path),
        "kit_name": kit_name,
        "output_format": output_format.value,
        "succeeded": sum(item.status is BatchStatus.SUCCEEDED for item in items),
        "failed": sum(item.status is BatchStatus.FAILED for item in items),
        "items": [
            {
                "sample_id": item.sample_id,
                "status": item.status.value,
                "output_file": item.output_path.name if item.output_path else None,
                "error": item.error,
            }
            for item in items
        ],
    }
    if batch_error is not None:
        manifest["batch_error"] = f"{type(batch_error).__name__}: {batch_error}"
    _atomic_write_text(
        manifest_path,
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
    )


def safe_output_stem(sample_id: str) -> str:
    """Return a deterministic, filesystem-safe stem for one sample identifier."""

    text = str(sample_id).strip()
    cleaned = "".join(
        character if character.isalnum() or character in "-_." else "_" for character in text
    )
    cleaned = cleaned.strip(" ._")
    return cleaned[:120] or "sample"


__all__ = [
    "BatchRenderItem",
    "BatchRenderResult",
    "render_genemapper_batch",
    "safe_output_stem",
]
