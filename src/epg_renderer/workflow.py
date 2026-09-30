"""High-level rendering workflows for parsed and manually entered profiles."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .kit_workflow import position_sample, resolve_kit
from .manual_profile import ManualProfile
from .parser import read_genotypes_table
from .positions import PositioningIssue
from .render_document import render_positioned_sample_svg
from .render_io import write_epg_output
from .render_options import RasterRenderOptions, SampleSelectionError, SvgRenderOptions

OMITTED_PEAK_ISSUE_CODES = frozenset(
    {
        "unknown_allele",
        "off_ladder_without_size",
        "missing_height",
        "measured_size_outside_range",
    }
)


@dataclass(frozen=True, slots=True)
class RenderReport:
    """One completed rendering plus every diagnostic an application must surface."""

    output_path: Path
    warnings: tuple[str, ...]
    issues: tuple[PositioningIssue, ...]

    @property
    def has_omitted_peaks(self) -> bool:
        """Return whether a called peak is missing from the rendered image."""

        return any(issue.code in OMITTED_PEAK_ISSUE_CODES for issue in self.issues)

    def messages(self) -> tuple[str, ...]:
        """Return every diagnostic as one ordered tuple of readable lines."""

        return (*self.warnings, *(issue_message(issue) for issue in self.issues))


def issue_message(issue: PositioningIssue) -> str:
    """Return one positioning issue as a readable, location-prefixed line."""

    location = issue.marker if issue.allele is None else f"{issue.marker} allele {issue.allele}"
    return f"{location}: {issue.message}"


DIAGNOSTICS_HEADING = "Please review before using this image:"


def format_diagnostics(messages: Sequence[str]) -> str:
    """Return one readable block for every diagnostic, or an empty string for none."""

    if not messages:
        return ""
    return "\n".join((DIAGNOSTICS_HEADING, *(f"\u2022 {text}" for text in messages)))


def render_genemapper_epg_report(
    input_path: str | Path,
    output_path: str | Path,
    *,
    sample_id: str | None = None,
    kit_name: str | None = None,
    options: SvgRenderOptions | None = None,
    raster_options: RasterRenderOptions | None = None,
    strict_positioning: bool = True,
    sample_id_column: str | None = None,
) -> RenderReport:
    """Render one GeneMapper sample and return its output path with all diagnostics.

    Applications must present the returned warnings and issues. A rendered image
    can omit called peaks, and nothing else tells the user that it did.
    """

    if sample_id_column is None:
        project = read_genotypes_table(input_path)
    else:
        project = read_genotypes_table(input_path, sample_id_column=sample_id_column)

    available = project.sample_ids
    if sample_id is None:
        if len(available) != 1:
            raise SampleSelectionError(
                "sample_id is required when the GeneMapper export contains "
                f"{len(available)} samples: {available!r}."
            )
        selected_id = available[0]
    else:
        selected_id = str(sample_id)
        if selected_id not in project.samples:
            raise SampleSelectionError(
                f"Sample {selected_id!r} was not found. Available samples: {available!r}."
            )

    sample = project.sample(selected_id)
    match = resolve_kit(sample, kit_name=kit_name, require_genemapper_compatible=True)
    positioned = position_sample(
        sample,
        kit_name=match.kit.name,
        strict=strict_positioning,
        require_genemapper_compatible=True,
    )
    svg = render_positioned_sample_svg(positioned, options=options)
    written = write_epg_output(svg, output_path, raster_options=raster_options)
    return RenderReport(
        output_path=written,
        warnings=tuple(project.warnings),
        issues=tuple(positioned.issues),
    )


def render_genemapper_epg(
    input_path: str | Path,
    output_path: str | Path,
    *,
    sample_id: str | None = None,
    kit_name: str | None = None,
    options: SvgRenderOptions | None = None,
    raster_options: RasterRenderOptions | None = None,
    strict_positioning: bool = True,
    sample_id_column: str | None = None,
) -> Path:
    """Render one sample from a GeneMapper export to SVG, PNG, or JPEG.

    A sample identifier is required when the export contains more than one sample.
    Only kits explicitly marked as GeneMapper-compatible can be used through this
    high-level workflow. Use `render_genemapper_epg_report` when the calling
    application should also present parser warnings and positioning issues.
    """

    return render_genemapper_epg_report(
        input_path,
        output_path,
        sample_id=sample_id,
        kit_name=kit_name,
        options=options,
        raster_options=raster_options,
        strict_positioning=strict_positioning,
        sample_id_column=sample_id_column,
    ).output_path


def render_manual_epg_report(
    profile: ManualProfile,
    output_path: str | Path,
    *,
    options: SvgRenderOptions | None = None,
    raster_options: RasterRenderOptions | None = None,
    strict_positioning: bool = True,
) -> RenderReport:
    """Render one validated manual profile and return its diagnostics."""

    sample = profile.to_sample_call()
    match = resolve_kit(sample, kit_name=profile.kit_name, require_genemapper_compatible=False)
    positioned = position_sample(
        sample,
        kit_name=match.kit.name,
        strict=strict_positioning,
        require_genemapper_compatible=False,
    )
    svg = render_positioned_sample_svg(positioned, options=options)
    written = write_epg_output(svg, output_path, raster_options=raster_options)
    return RenderReport(output_path=written, warnings=(), issues=tuple(positioned.issues))


def render_manual_epg(
    profile: ManualProfile,
    output_path: str | Path,
    *,
    options: SvgRenderOptions | None = None,
    raster_options: RasterRenderOptions | None = None,
    strict_positioning: bool = True,
) -> Path:
    """Render one validated manual profile to SVG, PNG, or JPEG."""

    return render_manual_epg_report(
        profile,
        output_path,
        options=options,
        raster_options=raster_options,
        strict_positioning=strict_positioning,
    ).output_path


__all__ = [
    "DIAGNOSTICS_HEADING",
    "OMITTED_PEAK_ISSUE_CODES",
    "RenderReport",
    "format_diagnostics",
    "issue_message",
    "render_genemapper_epg",
    "render_genemapper_epg_report",
    "render_manual_epg",
    "render_manual_epg_report",
]
