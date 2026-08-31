"""High-level rendering workflows for parsed and manually entered profiles."""

from __future__ import annotations

from pathlib import Path

from .manual_profile import ManualProfile
from .parser import read_genotypes_table
from .render_document import render_sample_svg
from .render_io import write_epg_output
from .render_options import RasterRenderOptions, SampleSelectionError, SvgRenderOptions


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
    high-level workflow.
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

    svg = render_sample_svg(
        project.sample(selected_id),
        kit_name=kit_name,
        options=options,
        strict_positioning=strict_positioning,
        require_genemapper_compatible=True,
    )
    return write_epg_output(svg, output_path, raster_options=raster_options)


def render_manual_epg(
    profile: ManualProfile,
    output_path: str | Path,
    *,
    options: SvgRenderOptions | None = None,
    raster_options: RasterRenderOptions | None = None,
    strict_positioning: bool = True,
) -> Path:
    """Render one validated manual profile to SVG, PNG, or JPEG."""

    svg = render_sample_svg(
        profile.to_sample_call(),
        kit_name=profile.kit_name,
        options=options,
        strict_positioning=strict_positioning,
        require_genemapper_compatible=False,
    )
    return write_epg_output(svg, output_path, raster_options=raster_options)


__all__ = ["render_genemapper_epg", "render_manual_epg"]
