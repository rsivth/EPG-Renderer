"""Stable public API for loading, matching, positioning, and rendering EPG data."""

from __future__ import annotations

from pathlib import Path
from typing import overload

from .batch import BatchRenderResult, render_genemapper_batch
from .kit_registry import KitProfile, available_genemapper_kit_profiles, available_kit_profiles
from .kit_registry import get_kit_profile as _get_kit_profile
from .kit_workflow import KitMatch, detect_kits
from .kit_workflow import position_sample as _position_sample
from .models import GeneMapperProject, SampleCall
from .parser import read_genotypes_table
from .positions import KitCoordinateModel, PositionedSample
from .render_document import render_positioned_sample_svg, render_sample_svg
from .render_options import OutputFormat, RasterRenderOptions, SvgRenderOptions
from .workflow import render_genemapper_epg


def load_project(
    path: str | Path,
    *,
    sample_id_column: str = "Sample Name",
    marker_column: str = "Marker",
    dye_column: str | None = "Dye",
    delimiter: str | None = None,
    encoding: str | None = None,
    require_height: bool = True,
    export_mode: str = "unknown",
) -> GeneMapperProject:
    """Load and validate one GeneMapper genotype-table export.

    The returned project and all nested calls are immutable. Parser errors identify the
    source boundary that violated the expected GeneMapper table contract.
    """

    return read_genotypes_table(
        path,
        sample_id_column=sample_id_column,
        marker_column=marker_column,
        dye_column=dye_column,
        delimiter=delimiter,
        encoding=encoding,
        require_height=require_height,
        export_mode=export_mode,
    )


def list_kits(*, genemapper_only: bool = False) -> tuple[KitProfile, ...]:
    """Return bundled immutable kit profiles in deterministic resource order."""

    if genemapper_only:
        return available_genemapper_kit_profiles()
    return available_kit_profiles()


def load_kit(name: str) -> KitProfile:
    """Load one bundled kit profile by canonical name or declared alias."""

    return _get_kit_profile(name)


def match_kits(
    sample: SampleCall,
    *,
    genemapper_only: bool = False,
) -> tuple[KitMatch, ...]:
    """Rank bundled kit profiles against the markers, dyes, and order in a sample."""

    return detect_kits(sample, require_genemapper_compatible=genemapper_only)


def position_sample(
    sample: SampleCall,
    *,
    kit_name: str | None = None,
    coordinate_model: KitCoordinateModel | None = None,
    strict: bool = True,
    require_exact_bin_centres: bool = False,
    genemapper_only: bool = False,
) -> PositionedSample:
    """Map called alleles to kit-specific nominal fragment coordinates.

    Derived coordinates are schematic display positions unless the selected profile
    explicitly declares verified exact bin centres.
    """

    return _position_sample(
        sample,
        kit_name=kit_name,
        model=coordinate_model,
        strict=strict,
        require_exact_bin_centres=require_exact_bin_centres,
        require_genemapper_compatible=genemapper_only,
    )


@overload
def render_svg(
    sample: SampleCall,
    *,
    kit_name: str | None = None,
    options: SvgRenderOptions | None = None,
    strict_positioning: bool = True,
    genemapper_only: bool = False,
) -> str: ...


@overload
def render_svg(
    sample: PositionedSample,
    *,
    kit_name: None = None,
    options: SvgRenderOptions | None = None,
    strict_positioning: bool = True,
    genemapper_only: bool = False,
) -> str: ...


def render_svg(
    sample: SampleCall | PositionedSample,
    *,
    kit_name: str | None = None,
    options: SvgRenderOptions | None = None,
    strict_positioning: bool = True,
    genemapper_only: bool = False,
) -> str:
    """Render an unpositioned sample after resolving and applying a kit model."""
    """Render a sample that already contains nominal fragment coordinates."""
    """Render a parsed or already positioned sample as deterministic SVG text."""

    if isinstance(sample, PositionedSample):
        if kit_name is not None:
            raise ValueError("kit_name cannot be supplied for an already positioned sample.")
        return render_positioned_sample_svg(sample, options=options)
    return render_sample_svg(
        sample,
        kit_name=kit_name,
        options=options,
        strict_positioning=strict_positioning,
        require_genemapper_compatible=genemapper_only,
    )


def render_file(
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
    """Render one selected sample from a GeneMapper export to SVG, PNG, or JPEG."""

    return render_genemapper_epg(
        input_path,
        output_path,
        sample_id=sample_id,
        kit_name=kit_name,
        options=options,
        raster_options=raster_options,
        strict_positioning=strict_positioning,
        sample_id_column=sample_id_column,
    )


def render_batch(
    input_path: str | Path,
    output_dir: str | Path,
    *,
    output_format: OutputFormat = OutputFormat.SVG,
    kit_name: str | None = None,
    options: SvgRenderOptions | None = None,
    raster_options: RasterRenderOptions | None = None,
    strict_positioning: bool = True,
    sample_id_column: str | None = None,
    continue_on_error: bool = True,
) -> BatchRenderResult:
    """Render every sample in one GeneMapper export and write a JSON manifest."""

    return render_genemapper_batch(
        input_path,
        output_dir,
        output_format=output_format,
        kit_name=kit_name,
        options=options,
        raster_options=raster_options,
        strict_positioning=strict_positioning,
        sample_id_column=sample_id_column,
        continue_on_error=continue_on_error,
    )


__all__ = [
    "list_kits",
    "load_kit",
    "load_project",
    "match_kits",
    "position_sample",
    "render_batch",
    "render_file",
    "render_svg",
]
