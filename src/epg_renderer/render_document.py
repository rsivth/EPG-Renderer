"""SVG document planning and orchestration for positioned STR samples.

This module validates document-level inputs, prepares immutable rendering plans and
assembles the document in a deterministic child order. Channel-level geometry and SVG
primitives remain isolated in :mod:`epg_renderer.render_svg`.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal

from .domain import PeakHeightMode, ProfileOrigin
from .kit_registry import get_kit_profile
from .kit_schema import KitProfile
from .kit_workflow import resolve_and_position
from .kits import DyeChannel
from .models import SampleCall
from .positions import (
    MarkerCoordinateDefinition,
    PeakCoordinateSource,
    PositionedPeak,
    PositionedSample,
)
from .render_layout import (
    ChannelPlan,
    decimal_text,
    plan_channel_labels,
    resolve_x_domain,
    rfu_scale_maxima,
)
from .render_options import (
    SvgRenderError,
    SvgRenderOptions,
    UnpositionedPeakRenderError,
    UnpositionedPolicy,
    YellowChannelMode,
    _ValidatedOptions,
    validate_svg_options,
    validate_xml_text,
)
from .render_svg import (
    _add_style,
    _ChannelRenderContext,
    _q,
    _render_channel,
    _validate_positioned_sample,
)
from .version import __version__


@dataclass(frozen=True, slots=True)
class _SvgDocumentPlan:
    """All validated data required to construct one SVG document."""

    profile: KitProfile
    options: _ValidatedOptions
    usable_peaks: tuple[PositionedPeak, ...]
    omitted_count: int
    marker_annotation_counts: dict[str, int]
    marker_annotation_messages: tuple[str, ...]
    coordinate_provenance: str
    coordinate_source_counts: dict[str, int]
    coordinate_description: str
    x_min: Decimal
    x_max: Decimal
    plot_width: int
    ordered_channels: tuple[DyeChannel, ...]
    peaks_by_dye: dict[str, list[PositionedPeak]]
    scale_maxima: dict[str, int]
    markers_by_dye: dict[str, list[MarkerCoordinateDefinition]]
    channel_plans: dict[str, ChannelPlan]
    document_height: int
    title_text: str
    origin: ProfileOrigin
    height_mode: PeakHeightMode


def render_sample_svg(
    sample: SampleCall,
    *,
    kit_name: str | None = None,
    options: SvgRenderOptions | None = None,
    strict_positioning: bool = True,
    require_genemapper_compatible: bool = False,
) -> str:
    """Resolve, position, and render one parsed sample as SVG."""

    positioned = resolve_and_position(
        sample,
        kit_name=kit_name,
        strict=strict_positioning,
        require_genemapper_compatible=require_genemapper_compatible,
    )
    return render_positioned_sample_svg(positioned, options=options)


def render_positioned_sample_svg(
    positioned: PositionedSample,
    *,
    options: SvgRenderOptions | None = None,
) -> str:
    """Render one positioned sample as a deterministic self-contained SVG string."""

    opts = validate_svg_options(options or SvgRenderOptions())
    plan = _prepare_svg_document(positioned, opts)
    root = _create_svg_document(positioned, plan)
    channel_y = _render_document_channels(root, plan)
    _render_document_footer(root, plan, channel_y)
    ET.indent(root, space="  ")
    body = ET.tostring(root, encoding="unicode", short_empty_elements=True)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + body + "\n"


def _prepare_svg_document(
    positioned: PositionedSample,
    options: _ValidatedOptions,
) -> _SvgDocumentPlan:
    profile = _validated_render_profile(positioned)
    usable_peaks, omitted_count = _select_usable_peaks(positioned.peaks, options)
    marker_annotation_counts = _marker_annotation_counts(positioned.peaks)
    marker_annotation_messages = _marker_annotation_messages(marker_annotation_counts)
    coordinate_source_counts = _coordinate_source_counts(usable_peaks)
    coordinate_provenance = _coordinate_provenance(coordinate_source_counts)
    coordinate_description = _coordinate_description(coordinate_source_counts)
    x_min, x_max = resolve_x_domain(profile.coordinate_model.markers, options)
    _validate_peaks_in_domain(usable_peaks, x_min, x_max)
    plot_width = _validated_plot_width(options)
    peaks_by_dye = _group_peaks_by_dye(usable_peaks)
    ordered_channels = tuple(sorted(profile.kit.channels, key=lambda item: item.order))
    scale_maxima = rfu_scale_maxima(
        ordered_channels,
        peaks_by_dye,
        options,
        height_mode=positioned.height_mode,
    )
    markers_by_dye = _group_markers_by_dye(profile.coordinate_model.markers)
    channel_plans = _plan_channel_layouts(
        ordered_channels,
        peaks_by_dye,
        options,
        x_min,
        x_max,
        height_mode=positioned.height_mode,
    )
    document_height = (
        options.header_height
        + sum(channel_plans[channel.code].height for channel in ordered_channels)
        + options.footer_height
        + _extra_footer_height(options, marker_annotation_messages)
    )
    title_text = options.title or positioned.display_name or positioned.sample_id
    validate_xml_text(title_text, "title")
    return _SvgDocumentPlan(
        profile=profile,
        options=options,
        usable_peaks=usable_peaks,
        omitted_count=omitted_count,
        marker_annotation_counts=marker_annotation_counts,
        marker_annotation_messages=marker_annotation_messages,
        coordinate_provenance=coordinate_provenance,
        coordinate_source_counts=coordinate_source_counts,
        coordinate_description=coordinate_description,
        x_min=x_min,
        x_max=x_max,
        plot_width=plot_width,
        ordered_channels=ordered_channels,
        peaks_by_dye=peaks_by_dye,
        scale_maxima=scale_maxima,
        markers_by_dye=markers_by_dye,
        channel_plans=channel_plans,
        document_height=document_height,
        title_text=title_text,
        origin=positioned.origin,
        height_mode=positioned.height_mode,
    )


def _validated_render_profile(positioned: PositionedSample) -> KitProfile:
    try:
        profile = get_kit_profile(positioned.kit_name)
    except KeyError as exc:
        raise SvgRenderError(f"No renderable kit definition for {positioned.kit_name!r}.") from exc
    coordinate_model = profile.coordinate_model
    metadata_matches = (
        positioned.coordinate_model_version == coordinate_model.model_version
        and positioned.coordinate_kind is coordinate_model.coordinate_kind
        and positioned.exact_bin_centres == coordinate_model.exact_bin_centres
    )
    if not metadata_matches:
        raise SvgRenderError(
            "Positioned sample coordinate metadata does not match a supported bundled kit model."
        )
    _validate_positioned_sample(positioned, profile.kit)
    return profile


def _select_usable_peaks(
    peaks: tuple[PositionedPeak, ...],
    options: _ValidatedOptions,
) -> tuple[tuple[PositionedPeak, ...], int]:
    usable: list[PositionedPeak] = []
    omitted_count = 0
    for peak in peaks:
        if peak.annotation_only:
            continue
        if peak.coordinate_bp is not None:
            usable.append(peak)
            continue
        if options.unpositioned_policy is UnpositionedPolicy.ERROR:
            raise UnpositionedPeakRenderError(
                f"Cannot render {peak.marker} allele {peak.allele!r}: "
                "no base-pair coordinate is available."
            )
        omitted_count += 1
    return tuple(usable), omitted_count


def _marker_annotation_counts(peaks: tuple[PositionedPeak, ...]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for peak in peaks:
        if peak.annotation_only:
            counts[peak.marker] += 1
    return dict(sorted(counts.items()))


def _marker_annotation_messages(marker_annotation_counts: dict[str, int]) -> tuple[str, ...]:
    return tuple(
        (f"Marker {marker} contains unpositioned off-ladder allele(s) without size information.")
        for marker in sorted(marker_annotation_counts)
    )


def _coordinate_source_counts(peaks: tuple[PositionedPeak, ...]) -> dict[str, int]:
    counts = Counter(peak.coordinate_source.value for peak in peaks)
    return dict(sorted(counts.items()))


def _coordinate_provenance(counts: dict[str, int]) -> str:
    if not counts:
        return PeakCoordinateSource.UNPOSITIONED.value
    if len(counts) == 1:
        return next(iter(counts))
    return "mixed"


def _coordinate_description(counts: dict[str, int]) -> str:
    descriptions = {
        PeakCoordinateSource.MEASURED.value: "measured fragment sizes exported by the source software",
        PeakCoordinateSource.NOMINAL.value: "nominal kit display coordinates",
        PeakCoordinateSource.ESTIMATED.value: "repeat-based estimated coordinates",
        PeakCoordinateSource.EXACT_BIN_CENTRE.value: "verified exact bin centres",
    }
    present = [
        descriptions[source.value] for source in PeakCoordinateSource if source.value in counts
    ]
    if not present:
        return "No positioned peak coordinates are represented."
    if len(present) == 1:
        sentence = f"Horizontal called-peak positions use {present[0]}."
        if (
            PeakCoordinateSource.NOMINAL.value in counts
            or PeakCoordinateSource.ESTIMATED.value in counts
        ):
            sentence = (
                sentence[:-1]
                + ", not measured fragment sizes or asserted exact GeneMapper bin centres."
            )
        elif PeakCoordinateSource.EXACT_BIN_CENTRE.value in counts:
            sentence = sentence[:-1] + ", not measured fragment sizes."
        return sentence
    if len(present) == 2:
        sources = f"{present[0]} and {present[1]}"
    else:
        sources = ", ".join(present[:-1]) + f", and {present[-1]}"
    return (
        f"Horizontal called-peak positions mix {sources}; each peak records its coordinate source."
    )


def _extra_footer_height(
    options: _ValidatedOptions,
    marker_annotation_messages: tuple[str, ...],
) -> int:
    if not marker_annotation_messages:
        return 0
    heading_height = 22
    line_height = 16
    spacing_after_disclaimer = 14 if options.show_disclaimer else 0
    return spacing_after_disclaimer + heading_height + len(marker_annotation_messages) * line_height


def _validate_peaks_in_domain(
    peaks: tuple[PositionedPeak, ...],
    x_min: Decimal,
    x_max: Decimal,
) -> None:
    outside = [
        peak
        for peak in peaks
        if peak.coordinate_bp is not None and not (x_min <= peak.coordinate_bp <= x_max)
    ]
    if not outside:
        return
    first = outside[0]
    raise SvgRenderError(
        f"The horizontal domain {x_min}–{x_max} bp excludes called peak "
        f"{first.marker} {first.allele} at {first.coordinate_bp} bp."
    )


def _validated_plot_width(options: _ValidatedOptions) -> int:
    plot_width = options.width - options.left_margin - options.right_margin
    if plot_width < 400:
        raise SvgRenderError("The plot area must be at least 400 pixels wide.")
    return plot_width


def _group_peaks_by_dye(
    peaks: tuple[PositionedPeak, ...],
) -> dict[str, list[PositionedPeak]]:
    grouped: dict[str, list[PositionedPeak]] = defaultdict(list)
    for peak in peaks:
        grouped[peak.dye].append(peak)
    for dye_peaks in grouped.values():
        dye_peaks.sort(key=lambda peak: (peak.coordinate_bp, peak.marker, peak.allele_index))
    return grouped


def _group_markers_by_dye(
    markers: tuple[MarkerCoordinateDefinition, ...],
) -> dict[str, list[MarkerCoordinateDefinition]]:
    grouped: dict[str, list[MarkerCoordinateDefinition]] = defaultdict(list)
    for marker in markers:
        grouped[marker.dye].append(marker)
    return grouped


def _plan_channel_layouts(
    channels: tuple[DyeChannel, ...],
    peaks_by_dye: dict[str, list[PositionedPeak]],
    options: _ValidatedOptions,
    x_min: Decimal,
    x_max: Decimal,
    *,
    height_mode: PeakHeightMode,
) -> dict[str, ChannelPlan]:
    plot_left = float(options.left_margin)
    plot_right = float(options.width - options.right_margin)
    return {
        channel.code: plan_channel_labels(
            peaks_by_dye.get(channel.code, []),
            options=options,
            height_mode=height_mode,
            x_min=x_min,
            x_max=x_max,
            plot_left=plot_left,
            plot_right=plot_right,
        )
        for channel in channels
    }


def _create_svg_document(
    positioned: PositionedSample,
    plan: _SvgDocumentPlan,
) -> ET.Element:
    options = plan.options
    root = ET.Element(
        _q("svg"),
        {
            "width": str(options.width),
            "height": str(plan.document_height),
            "viewBox": f"0 0 {options.width} {plan.document_height}",
            "role": "img",
            "aria-labelledby": "epg-title epg-description",
            "data-epg-renderer-version": __version__,
            "data-kit": positioned.kit_name,
            "data-coordinate-model-version": positioned.coordinate_model_version,
            "data-coordinate-kind": positioned.coordinate_kind.value,
            "data-exact-bin-centres": str(positioned.exact_bin_centres).lower(),
            "data-peak-coordinate-provenance": plan.coordinate_provenance,
            "data-profile-origin": positioned.origin.value,
            "data-peak-height-mode": positioned.height_mode.value,
        },
    )
    _add_document_accessibility(root, positioned, plan)
    _add_document_metadata(root, positioned, plan)
    _add_document_background(root, plan)
    _add_style(root, options.font_family)
    _add_document_heading(root, positioned, plan)
    return root


def _add_document_accessibility(
    root: ET.Element,
    positioned: PositionedSample,
    plan: _SvgDocumentPlan,
) -> None:
    ET.SubElement(root, _q("title"), {"id": "epg-title"}).text = plan.title_text
    if positioned.origin is ProfileOrigin.MANUAL:
        if positioned.height_mode is PeakHeightMode.UNIFORM:
            introduction = (
                "Manually entered schematic electropherogram with uniform, non-quantitative "
                "peak heights."
            )
        else:
            introduction = (
                "Manually entered schematic electropherogram using user-supplied allele and RFU "
                "values."
            )
    else:
        introduction = (
            "Schematic electropherogram reconstructed from called allele identifiers and RFU "
            "heights."
        )
    description = f"{introduction} {plan.coordinate_description}"
    ET.SubElement(root, _q("desc"), {"id": "epg-description"}).text = description


def _add_document_metadata(
    root: ET.Element,
    positioned: PositionedSample,
    plan: _SvgDocumentPlan,
) -> None:
    metadata = ET.SubElement(root, _q("metadata"))
    metadata.text = json.dumps(
        {
            "schema": f"epg-renderer-svg-metadata-{__version__}",
            "x_min_bp": decimal_text(plan.x_min),
            "x_max_bp": decimal_text(plan.x_max),
            "renderer_version": __version__,
            "sample_id": positioned.sample_id,
            "sample_display_name": positioned.display_name,
            "profile_origin": positioned.origin.value,
            "peak_height_mode": positioned.height_mode.value,
            "kit": positioned.kit_name,
            "coordinate_model_version": positioned.coordinate_model_version,
            "coordinate_kind": positioned.coordinate_kind.value,
            "exact_bin_centres": positioned.exact_bin_centres,
            "peak_coordinate_provenance": plan.coordinate_provenance,
            "peak_coordinate_source_counts": plan.coordinate_source_counts,
            "source_issue_count": len(positioned.issues),
            "omitted_unpositioned_peaks": plan.omitted_count,
            "marker_annotations": plan.marker_annotation_counts,
            "marker_annotation_messages": plan.marker_annotation_messages,
            "rfu_scale_mode": (
                plan.options.rfu_scale_mode.value
                if positioned.height_mode is PeakHeightMode.RFU
                else None
            ),
            "yellow_channel_mode": plan.options.yellow_channel_mode.value,
            "channel_label_lanes": {
                channel.code: plan.channel_plans[channel.code].lane_count
                for channel in plan.ordered_channels
            },
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _add_document_background(root: ET.Element, plan: _SvgDocumentPlan) -> None:
    ET.SubElement(
        root,
        _q("rect"),
        {
            "x": "0",
            "y": "0",
            "width": str(plan.options.width),
            "height": str(plan.document_height),
            "fill": "#FFFFFF",
        },
    )


def _add_document_heading(
    root: ET.Element,
    positioned: PositionedSample,
    plan: _SvgDocumentPlan,
) -> None:
    options = plan.options
    ET.SubElement(
        root,
        _q("text"),
        {"x": str(options.left_margin), "y": "31", "class": "document-title"},
    ).text = plan.title_text
    source_text = ""
    peak_count_label = "called peaks"
    if positioned.origin is ProfileOrigin.MANUAL:
        peak_count_label = "entered peaks"
        source_text = (
            " · manually entered schematic profile"
            if positioned.height_mode is PeakHeightMode.RFU
            else " · manually entered profile with uniform non-quantitative peak heights"
        )
    ET.SubElement(
        root,
        _q("text"),
        {"x": str(options.left_margin), "y": "53", "class": "document-subtitle"},
    ).text = (
        f"Kit: {plan.profile.display_name} ({plan.profile.manufacturer}) · "
        f"nominal coordinate model {positioned.coordinate_model_version} · "
        f"{peak_count_label}: {len(plan.usable_peaks)}{source_text}"
    )


def _render_document_channels(root: ET.Element, plan: _SvgDocumentPlan) -> int:
    channel_y = plan.options.header_height
    for channel in plan.ordered_channels:
        channel_plan = plan.channel_plans[channel.code]
        _render_channel(
            _ChannelRenderContext(
                root=root,
                channel=channel,
                channel_y=channel_y,
                plan=channel_plan,
                options=plan.options,
                plot_width=plan.plot_width,
                x_min=plan.x_min,
                x_max=plan.x_max,
                max_rfu=plan.scale_maxima[channel.code],
                peaks=plan.peaks_by_dye.get(channel.code, []),
                marker_definitions=tuple(plan.markers_by_dye[channel.code]),
                marker_annotation_counts={
                    marker.marker: plan.marker_annotation_counts.get(marker.marker, 0)
                    for marker in plan.markers_by_dye[channel.code]
                    if plan.marker_annotation_counts.get(marker.marker, 0)
                },
                color=_channel_display_color(plan, channel),
            )
        )
        channel_y += channel_plan.height
    return channel_y


def _channel_display_color(plan: _SvgDocumentPlan, channel: DyeChannel) -> str:
    if (
        plan.options.yellow_channel_mode is YellowChannelMode.BLACK
        and channel.color_name.casefold() == "yellow"
    ):
        return "#202124"
    return plan.profile.channel_color(channel.code)


def _render_document_footer(root: ET.Element, plan: _SvgDocumentPlan, channel_y: int) -> None:
    footer_y = channel_y + 24
    current_y = footer_y
    if plan.options.show_disclaimer:
        _add_disclaimer(root, plan, current_y)
        current_y += 28
    if plan.omitted_count:
        ET.SubElement(
            root,
            _q("text"),
            {
                "x": str(plan.options.width - plan.options.right_margin),
                "y": str(footer_y),
                "text-anchor": "end",
                "class": "warning",
                "data-omitted-unpositioned-peaks": str(plan.omitted_count),
            },
        ).text = f"Omitted unpositioned peaks: {plan.omitted_count}"
    if plan.marker_annotation_messages:
        current_y += 14
        _add_marker_annotation_legend(
            root, plan.options, current_y, plan.marker_annotation_messages
        )


def _add_marker_annotation_legend(
    root: ET.Element,
    options: _ValidatedOptions,
    legend_y: int,
    messages: tuple[str, ...],
) -> None:
    ET.SubElement(
        root,
        _q("text"),
        {"x": str(options.left_margin), "y": str(legend_y), "class": "legend-heading"},
    ).text = "Marker annotations"
    for index, message in enumerate(messages):
        item_y = legend_y + 16 + index * 16
        group = ET.SubElement(
            root,
            _q("g"),
            {
                "class": "marker-annotation-legend-item",
                "data-legend-index": str(index),
            },
        )
        ET.SubElement(
            group,
            _q("rect"),
            {
                "x": str(options.left_margin),
                "y": str(item_y - 8),
                "width": "14",
                "height": "8",
                "rx": "1.5",
                "transform": f"rotate(45 {options.left_margin + 7} {item_y - 4})",
                "fill": "#F28C00",
                "stroke": "#B85F00",
                "stroke-width": "0.8",
                "class": "legend-ribbon-swatch",
            },
        )
        ET.SubElement(
            group,
            _q("text"),
            {
                "x": str(options.left_margin + 24),
                "y": str(item_y),
                "class": "legend-text",
                "data-legend-message": "off-ladder-no-size",
            },
        ).text = message


def _add_disclaimer(root: ET.Element, plan: _SvgDocumentPlan, footer_y: int) -> None:
    options = plan.options
    if plan.origin is ProfileOrigin.MANUAL:
        if plan.height_mode is PeakHeightMode.UNIFORM:
            first_line = (
                "Manually entered schematic profile: uniform peak heights are non-quantitative; "
                "no RFU measurements are represented."
            )
        else:
            first_line = (
                "Manually entered schematic profile: only user-entered alleles and RFU values "
                "are shown; no analytical source file is represented."
            )
    else:
        first_line = (
            "Schematic reconstruction: only peaks called in the GeneMapper genotype export are "
            "shown. No baseline, uncalled artefacts or additional stutter peaks are generated."
        )
    ET.SubElement(
        root,
        _q("text"),
        {"x": str(options.left_margin), "y": str(footer_y), "class": "disclaimer"},
    ).text = first_line
    ET.SubElement(
        root,
        _q("text"),
        {"x": str(options.left_margin), "y": str(footer_y + 17), "class": "disclaimer"},
    ).text = plan.coordinate_description


__all__ = ["render_positioned_sample_svg", "render_sample_svg"]
