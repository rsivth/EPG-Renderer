"""Deterministic channel drawing and SVG geometry primitives."""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from decimal import Decimal

from .domain import PeakHeightMode
from .kits import DyeChannel, KitDefinition
from .positions import (
    MarkerCoordinateDefinition,
    PeakCoordinateSource,
    PositionedPeak,
    PositionedSample,
)
from .render_layout import (
    ChannelPlan,
    LabelPlacement,
    _estimate_bold_text_width,
    decimal_text,
    float_text,
    ticks,
    x_to_px,
)
from .render_metrics import _LABEL_METRICS, _MARKER_LABEL_METRICS, _TYPOGRAPHY_METRICS
from .render_options import (
    SvgRenderError,
    _ValidatedOptions,
    validate_xml_text,
)
from .rfu import validate_rfu

_SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", _SVG_NS)

_CHANNEL_PANEL_LEFT_EXTENSION_PX = 58
_CHANNEL_LABEL_LEFT_PADDING_PX = 10


@dataclass(frozen=True, slots=True)
class _ChannelRenderContext:
    root: ET.Element
    channel: DyeChannel
    channel_y: int
    plan: ChannelPlan
    options: _ValidatedOptions
    plot_width: int
    x_min: Decimal
    x_max: Decimal
    max_rfu: int
    peaks: list[PositionedPeak]
    marker_definitions: tuple[MarkerCoordinateDefinition, ...]
    marker_annotation_counts: dict[str, int]
    color: str


@dataclass(frozen=True, slots=True)
class _ChannelGeometry:
    plot_left: float
    plot_right: float
    marker_y: int
    marker_height: int
    signal_top: int
    signal_bottom: int
    label_lane_height: int
    label_box_height: int
    label_box_top_base_offset: int


@dataclass(frozen=True, slots=True)
class _PeakGeometry:
    x_positions: tuple[float, ...]
    half_width_px: float
    connectors: tuple[tuple[float, float, float, float], ...]


def _required_coordinate_bp(peak: PositionedPeak) -> Decimal:
    if peak.coordinate_bp is None:
        raise SvgRenderError(f"Peak {peak.marker} {peak.allele!r} has no coordinate.")
    return peak.coordinate_bp


def _render_channel(context: _ChannelRenderContext) -> None:
    """Render one dye channel with collision-free labels below a segmented baseline."""

    geometry = _channel_geometry(context)
    group = _create_channel_group(context, geometry)
    _render_marker_bands(group, context, geometry)
    _render_horizontal_grid(group, context, geometry)
    peak_geometry = _plan_peak_geometry(context, geometry)
    _render_x_axis(group, context, geometry, peak_geometry)
    _render_segmented_baseline(group, context, geometry, peak_geometry)
    if context.plan.height_mode is PeakHeightMode.RFU:
        _render_rfu_labels(group, context, geometry)
    if not context.peaks:
        _render_empty_channel(group, geometry)
        return
    _render_connectors(group, context, peak_geometry)
    _render_peaks(group, context, geometry, peak_geometry)


def _channel_geometry(context: _ChannelRenderContext) -> _ChannelGeometry:
    options = context.options
    plot_left = float(options.left_margin)
    plot_right = float(options.width - options.right_margin)
    marker_y = context.channel_y + 22
    marker_height = _MARKER_LABEL_METRICS.band_height_px
    signal_top = context.channel_y + _LABEL_METRICS.signal_top_offset_px
    label_lane_height = _LABEL_METRICS.lane_height_px
    label_box_height = (
        _LABEL_METRICS.rfu_box_height_px
        if context.plan.height_mode is PeakHeightMode.RFU
        else _LABEL_METRICS.uniform_box_height_px
    )
    label_box_top_base_offset = _LABEL_METRICS.box_top_offset_px
    base_label_area_height = (
        _LABEL_METRICS.label_area_bottom_padding_px
        + max(1, context.plan.lane_count) * label_lane_height
    )
    signal_bottom = context.channel_y + context.plan.height - base_label_area_height
    if signal_bottom - signal_top < _LABEL_METRICS.minimum_signal_height_px:
        raise SvgRenderError("channel_height leaves insufficient signal plotting space.")
    return _ChannelGeometry(
        plot_left=plot_left,
        plot_right=plot_right,
        marker_y=marker_y,
        marker_height=marker_height,
        signal_top=signal_top,
        signal_bottom=signal_bottom,
        label_lane_height=label_lane_height,
        label_box_height=label_box_height,
        label_box_top_base_offset=label_box_top_base_offset,
    )


def _create_channel_group(
    context: _ChannelRenderContext,
    geometry: _ChannelGeometry,
) -> ET.Element:
    options = context.options
    channel = context.channel
    attributes = {
        "class": "channel-panel",
        "data-dye": channel.code,
        "data-channel-label": channel.label,
        "data-peak-height-mode": context.plan.height_mode.value,
        "data-signal-top": float_text(float(geometry.signal_top)),
        "data-baseline-y": float_text(float(geometry.signal_bottom)),
        "data-label-lanes": str(context.plan.lane_count),
        "data-panel-height": str(context.plan.height),
        "data-display-color": context.color,
        "transform": "translate(0 0)",
    }
    if context.plan.height_mode is PeakHeightMode.RFU:
        attributes["data-rfu-max"] = str(context.max_rfu)
    group = ET.SubElement(context.root, _q("g"), attributes)
    ET.SubElement(
        group,
        _q("rect"),
        {
            "x": str(options.left_margin - _CHANNEL_PANEL_LEFT_EXTENSION_PX),
            "y": str(context.channel_y + 2),
            "width": str(
                options.width
                - options.left_margin
                - options.right_margin
                + _CHANNEL_PANEL_LEFT_EXTENSION_PX
            ),
            "height": str(context.plan.height - 6),
            "rx": "4",
            "class": "panel-background",
        },
    )
    ET.SubElement(
        group,
        _q("text"),
        {
            "x": str(
                options.left_margin
                - _CHANNEL_PANEL_LEFT_EXTENSION_PX
                + _CHANNEL_LABEL_LEFT_PADDING_PX
            ),
            "y": str(context.channel_y + 17),
            "text-anchor": "start",
            "class": "channel-label",
            "fill": context.color,
        },
    ).text = channel.label
    ET.SubElement(
        group,
        _q("text"),
        {
            "x": str(options.width - options.right_margin),
            "y": str(context.channel_y + 16),
            "text-anchor": "end",
            "class": "axis-unit",
        },
    ).text = "bp"
    return group


def _render_marker_bands(
    group: ET.Element,
    context: _ChannelRenderContext,
    geometry: _ChannelGeometry,
) -> None:
    if not context.options.show_marker_bands:
        return
    for marker in context.marker_definitions:
        start_x = x_to_px(
            marker.range_min_bp,
            context.x_min,
            context.x_max,
            geometry.plot_left,
            geometry.plot_right,
        )
        end_x = x_to_px(
            marker.range_max_bp,
            context.x_min,
            context.x_max,
            geometry.plot_left,
            geometry.plot_right,
        )
        start_x = max(geometry.plot_left, min(geometry.plot_right, start_x))
        end_x = max(geometry.plot_left, min(geometry.plot_right, end_x))
        if end_x <= start_x:
            continue
        band_width = end_x - start_x
        marker_group = ET.SubElement(
            group,
            _q("g"),
            {
                "class": "marker-band",
                "data-marker": marker.marker,
                "data-range-min-bp": decimal_text(marker.range_min_bp),
                "data-range-max-bp": decimal_text(marker.range_max_bp),
                "data-dye": context.channel.code,
            },
        )
        ET.SubElement(
            marker_group,
            _q("rect"),
            {
                "x": float_text(start_x),
                "y": str(geometry.marker_y),
                "width": float_text(band_width),
                "height": str(geometry.marker_height),
                "fill": "#F3F4F6",
                "stroke": "#000000",
                "stroke-width": "0.9",
            },
        )
        display_name = _marker_display_name(marker.marker)
        fitted_label, font_size = _fit_marker_label_text(display_name, band_width=band_width)
        if display_name != marker.marker:
            font_size = _MARKER_LABEL_METRICS.fallback_font_size_px
        text_attrs = {
            "x": float_text((start_x + end_x) / 2),
            "y": str(geometry.marker_y + _MARKER_LABEL_METRICS.baseline_offset_px),
            "text-anchor": "middle",
            "class": "marker-label",
            "fill": "#000000",
        }
        if font_size is not None:
            text_attrs["font-size"] = float_text(font_size)
        ET.SubElement(marker_group, _q("text"), text_attrs).text = fitted_label
        badge_count = context.marker_annotation_counts.get(marker.marker, 0)
        if badge_count:
            _render_marker_annotation_ribbon(
                marker_group,
                marker=marker.marker,
                start_x=start_x,
                end_x=end_x,
                marker_y=geometry.marker_y,
                count=badge_count,
            )


def _render_horizontal_grid(
    group: ET.Element,
    context: _ChannelRenderContext,
    geometry: _ChannelGeometry,
) -> None:
    if not context.options.show_grid or context.plan.height_mode is PeakHeightMode.UNIFORM:
        return
    for fraction in (0.25, 0.5, 0.75, 1.0):
        y = geometry.signal_bottom - fraction * (geometry.signal_bottom - geometry.signal_top)
        ET.SubElement(
            group,
            _q("line"),
            {
                "x1": float_text(geometry.plot_left),
                "x2": float_text(geometry.plot_right),
                "y1": float_text(y),
                "y2": float_text(y),
                "class": "horizontal-grid",
            },
        )


def _plan_peak_geometry(
    context: _ChannelRenderContext,
    geometry: _ChannelGeometry,
) -> _PeakGeometry:
    x_positions = tuple(
        x_to_px(
            _required_coordinate_bp(peak),
            context.x_min,
            context.x_max,
            geometry.plot_left,
            geometry.plot_right,
        )
        for peak in context.peaks
    )
    bp_to_px = context.plot_width / float(context.x_max - context.x_min)
    half_width_px = max(
        2.2,
        min(7.0, float(context.options.peak_half_width_bp) * bp_to_px),
    )
    connectors = tuple(
        (
            peak_x,
            float(geometry.signal_bottom),
            placement.x,
            float(
                geometry.signal_bottom
                + geometry.label_box_top_base_offset
                + placement.lane * geometry.label_lane_height
            ),
        )
        for peak_x, placement in zip(x_positions, context.plan.placements, strict=False)
    )
    return _PeakGeometry(x_positions, half_width_px, connectors)


def _render_x_axis(
    group: ET.Element,
    context: _ChannelRenderContext,
    geometry: _ChannelGeometry,
    peak_geometry: _PeakGeometry,
) -> None:
    options = context.options
    for tick in ticks(context.x_min, context.x_max, options.x_tick_interval_bp):
        x = x_to_px(
            Decimal(tick),
            context.x_min,
            context.x_max,
            geometry.plot_left,
            geometry.plot_right,
        )
        ET.SubElement(
            group,
            _q("line"),
            {
                "x1": float_text(x),
                "x2": float_text(x),
                "y1": str(geometry.signal_top),
                "y2": str(geometry.signal_bottom),
                "class": "vertical-grid" if options.show_grid else "tick-line",
            },
        )
        label_rect = (
            x - 14.0,
            geometry.signal_bottom + 3.0,
            x + 14.0,
            geometry.signal_bottom + 17.0,
        )
        if any(
            _segment_intersects_rect(connector, label_rect)
            for connector in peak_geometry.connectors
        ):
            ET.SubElement(
                group,
                _q("g"),
                {
                    "class": "axis-label-omission",
                    "data-tick": str(tick),
                    "data-reason": "connector-collision",
                },
            )
        else:
            ET.SubElement(
                group,
                _q("text"),
                {
                    "x": float_text(x),
                    "y": str(geometry.signal_bottom + 14),
                    "text-anchor": "middle",
                    "class": "axis-label",
                },
            ).text = str(tick)


def _render_segmented_baseline(
    group: ET.Element,
    context: _ChannelRenderContext,
    geometry: _ChannelGeometry,
    peak_geometry: _PeakGeometry,
) -> None:
    peak_intervals = _merge_intervals(
        [
            (
                max(geometry.plot_left, x - peak_geometry.half_width_px),
                min(geometry.plot_right, x + peak_geometry.half_width_px),
            )
            for x in peak_geometry.x_positions
        ]
    )
    baseline_group = ET.SubElement(
        group,
        _q("g"),
        {"class": "segmented-baseline"},
    )
    cursor = geometry.plot_left
    for left, right in peak_intervals:
        if left > cursor:
            _add_baseline_segment(
                baseline_group,
                cursor,
                left,
                geometry.signal_bottom,
                context.color,
            )
        cursor = max(cursor, right)
    if cursor < geometry.plot_right:
        _add_baseline_segment(
            baseline_group,
            cursor,
            geometry.plot_right,
            geometry.signal_bottom,
            context.color,
        )


def _add_baseline_segment(
    group: ET.Element,
    start: float,
    end: float,
    baseline_y: int,
    color: str,
) -> None:
    ET.SubElement(
        group,
        _q("line"),
        {
            "x1": float_text(start),
            "x2": float_text(end),
            "y1": str(baseline_y),
            "y2": str(baseline_y),
            "class": "axis-line channel-baseline-segment",
            "stroke": color,
            "stroke-width": "1.5",
            "stroke-linecap": "round",
        },
    )


def _render_rfu_labels(
    group: ET.Element,
    context: _ChannelRenderContext,
    geometry: _ChannelGeometry,
) -> None:
    for fraction, value in (
        (1.0, context.max_rfu),
        (0.5, context.max_rfu // 2),
        (0.0, 0),
    ):
        y = geometry.signal_bottom - fraction * (geometry.signal_bottom - geometry.signal_top)
        ET.SubElement(
            group,
            _q("text"),
            {
                "x": str(context.options.left_margin - 14),
                "y": float_text(y + 4),
                "text-anchor": "end",
                "class": "rfu-label",
                "data-rfu-tick": str(value),
            },
        ).text = str(value)


def _render_empty_channel(
    group: ET.Element,
    geometry: _ChannelGeometry,
) -> None:
    ET.SubElement(
        group,
        _q("text"),
        {
            "x": float_text((geometry.plot_left + geometry.plot_right) / 2),
            "y": str((geometry.signal_top + geometry.signal_bottom) // 2),
            "text-anchor": "middle",
            "class": "empty-channel",
        },
    ).text = "No called peaks"


def _render_connectors(
    group: ET.Element,
    context: _ChannelRenderContext,
    peak_geometry: _PeakGeometry,
) -> None:
    connector_layer = ET.SubElement(group, _q("g"), {"class": "connector-layer"})
    for index, (peak, connector) in enumerate(
        zip(context.peaks, peak_geometry.connectors, strict=False)
    ):
        x1, y1, x2, y2 = connector
        ET.SubElement(
            connector_layer,
            _q("line"),
            {
                "x1": float_text(x1),
                "x2": float_text(x2),
                "y1": float_text(y1),
                "y2": float_text(y2),
                "stroke": "#000000",
                "stroke-width": "0.8",
                "class": "allele-label-connector",
                "data-peak-index": str(index),
                "data-marker": peak.marker,
                "data-allele": peak.allele,
            },
        )


def _render_peaks(
    group: ET.Element,
    context: _ChannelRenderContext,
    geometry: _ChannelGeometry,
    peak_geometry: _PeakGeometry,
) -> None:
    peak_layer = ET.SubElement(group, _q("g"), {"class": "peak-and-label-layer"})
    triples = zip(
        context.peaks,
        peak_geometry.x_positions,
        context.plan.placements,
        strict=False,
    )
    for index, (peak, peak_x, placement) in enumerate(triples):
        if context.plan.height_mode is PeakHeightMode.UNIFORM:
            peak_y = float(geometry.signal_top)
        else:
            if peak.height is None:
                raise SvgRenderError(f"Peak {peak.marker} {peak.allele} has no RFU height.")
            peak_y = geometry.signal_bottom - (peak.height / context.max_rfu) * (
                geometry.signal_bottom - geometry.signal_top
            )
        peak_y = max(
            float(geometry.signal_top),
            min(float(geometry.signal_bottom), peak_y),
        )
        box_top = (
            geometry.signal_bottom
            + geometry.label_box_top_base_offset
            + placement.lane * geometry.label_lane_height
        )
        coordinate_text = decimal_text(_required_coordinate_bp(peak))
        attributes = {
            "class": "called-peak",
            "data-peak-index": str(index),
            "data-marker": peak.marker,
            "data-allele": peak.allele,
            "data-height-mode": context.plan.height_mode.value,
            "data-coordinate-bp": coordinate_text,
            "data-coordinate-source": peak.coordinate_source.value,
            "data-dye": peak.dye,
            "data-label-lane": str(placement.lane),
            "data-label-collision": "false",
            "data-x-px": float_text(peak_x),
            "data-y-px": float_text(peak_y),
            "data-label-box-x": float_text(placement.x - placement.width / 2),
            "data-label-box-y": float_text(box_top),
            "data-label-box-width": float_text(placement.width),
            "data-label-box-height": str(geometry.label_box_height),
        }
        source_attribute = {
            PeakCoordinateSource.MEASURED: "data-measured-bp",
            PeakCoordinateSource.NOMINAL: "data-nominal-bp",
            PeakCoordinateSource.ESTIMATED: "data-estimated-bp",
            PeakCoordinateSource.EXACT_BIN_CENTRE: "data-exact-bin-centre-bp",
        }.get(peak.coordinate_source)
        if source_attribute is not None:
            attributes[source_attribute] = coordinate_text
        if peak.height is not None:
            attributes["data-rfu"] = str(peak.height)
        if peak.source_dye is not None:
            attributes["data-source-dye"] = peak.source_dye
        peak_group = ET.SubElement(peak_layer, _q("g"), attributes)
        _render_peak_shape(
            peak_group,
            peak_x,
            peak_y,
            geometry,
            peak_geometry.half_width_px,
            context.color,
        )
        _render_peak_label(
            peak_group,
            peak,
            placement,
            box_top,
            geometry,
            height_mode=context.plan.height_mode,
        )


def _render_peak_shape(
    peak_group: ET.Element,
    peak_x: float,
    peak_y: float,
    geometry: _ChannelGeometry,
    half_width_px: float,
    color: str,
) -> None:
    left = peak_x - half_width_px
    right = peak_x + half_width_px
    shoulder_y = peak_y + (geometry.signal_bottom - peak_y) * 0.62
    path = (
        f"M {float_text(left)} {geometry.signal_bottom} "
        f"L {float_text(peak_x - half_width_px * 0.35)} "
        f"{float_text(shoulder_y)} "
        f"L {float_text(peak_x)} {float_text(peak_y)} "
        f"L {float_text(peak_x + half_width_px * 0.35)} "
        f"{float_text(shoulder_y)} "
        f"L {float_text(right)} {geometry.signal_bottom}"
    )
    ET.SubElement(
        peak_group,
        _q("path"),
        {
            "d": path,
            "fill": "#FFFFFF",
            "stroke": color,
            "stroke-width": "1.8",
            "stroke-linejoin": "round",
            "stroke-linecap": "butt",
            "class": "allele-peak-shape",
        },
    )


def _render_peak_label(
    peak_group: ET.Element,
    peak: PositionedPeak,
    placement: LabelPlacement,
    box_top: float,
    geometry: _ChannelGeometry,
    *,
    height_mode: PeakHeightMode,
) -> None:
    ET.SubElement(
        peak_group,
        _q("rect"),
        {
            "x": float_text(placement.x - placement.width / 2),
            "y": float_text(box_top),
            "width": float_text(placement.width),
            "height": str(geometry.label_box_height),
            "rx": "2",
            "fill": "#FFFFFF",
            "stroke": "#000000",
            "stroke-width": "0.9",
            "class": "allele-label-box",
        },
    )
    label = ET.SubElement(
        peak_group,
        _q("text"),
        {
            "x": float_text(placement.x),
            "y": float_text(box_top + _LABEL_METRICS.allele_baseline_offset_px),
            "text-anchor": "middle",
            "class": "peak-label",
            "fill": "#000000",
        },
    )
    ET.SubElement(
        label,
        _q("tspan"),
        {"x": float_text(placement.x), "class": "allele-label"},
    ).text = peak.allele
    if height_mode is PeakHeightMode.RFU:
        if peak.height is None:
            raise SvgRenderError(f"Peak {peak.marker} {peak.allele} has no RFU height.")
        ET.SubElement(
            label,
            _q("tspan"),
            {
                "x": float_text(placement.x),
                "dy": str(_LABEL_METRICS.height_line_offset_px),
                "class": "height-label",
            },
        ).text = str(peak.height)


def _marker_display_name(marker: str) -> str:
    normalized = "".join(character for character in marker.casefold() if character.isalnum())
    if normalized in {"amel", "amelogenin"}:
        return "A..."
    if normalized == "yindel":
        return "Y..."
    return marker


def _fit_marker_label_text(
    text: str,
    *,
    band_width: float,
    default_font_size: float | None = None,
    minimum_font_size: float | None = None,
) -> tuple[str, float | None]:
    """Fit a marker label into its band using optional truncation with ellipsis.

    The returned font size is ``None`` when the default marker-label CSS size is sufficient.
    Otherwise, a specific fallback size is returned. If even the fallback size does not fit,
    the text is truncated so that the visible label remains fully inside the marker band.
    """

    default_font_size = (
        _MARKER_LABEL_METRICS.font_size_px if default_font_size is None else default_font_size
    )
    minimum_font_size = (
        _MARKER_LABEL_METRICS.fallback_font_size_px
        if minimum_font_size is None
        else minimum_font_size
    )
    available_width = max(
        0.0,
        max(
            _MARKER_LABEL_METRICS.minimum_available_width_px,
            band_width - _MARKER_LABEL_METRICS.horizontal_padding_px,
        ),
    )
    if _estimate_bold_text_width(text, default_font_size) <= available_width:
        return text, None
    if _estimate_bold_text_width(text, minimum_font_size) <= available_width:
        return text, minimum_font_size

    ellipsis = "…"
    if _estimate_bold_text_width(ellipsis, minimum_font_size) > available_width:
        return ellipsis, minimum_font_size

    for end_index in range(len(text) - 1, 0, -1):
        candidate = f"{text[:end_index]}{ellipsis}"
        if _estimate_bold_text_width(candidate, minimum_font_size) <= available_width:
            return candidate, minimum_font_size
    return ellipsis, minimum_font_size


def _render_marker_annotation_ribbon(
    marker_group: ET.Element,
    *,
    marker: str,
    start_x: float,
    end_x: float,
    marker_y: int,
    count: int,
) -> None:
    band_width = end_x - start_x
    marker_height = float(_MARKER_LABEL_METRICS.band_height_px)
    top_y = float(marker_y)
    bottom_y = top_y + marker_height
    left_inset = 1.5
    right_gap = 6.5
    available_span = max(6.0, band_width - left_inset - right_gap)
    preferred_span = max(12.0, min(24.0, band_width * 0.55))
    stripe_span = min(preferred_span, available_span)
    slant = min(6.0, max(2.2, stripe_span * 0.18))
    half_width = max(1.6, (stripe_span / 2.0) - slant)
    center_x = end_x - right_gap - (half_width + slant)
    leftmost = center_x - half_width - slant
    if leftmost < start_x + left_inset:
        center_x += (start_x + left_inset) - leftmost
    rightmost = center_x + half_width + slant
    if rightmost > end_x - right_gap:
        center_x -= rightmost - (end_x - right_gap)
    points = (
        (center_x - half_width - slant, top_y),
        (center_x + half_width - slant, top_y),
        (center_x + half_width + slant, bottom_y),
        (center_x - half_width + slant, bottom_y),
    )
    ribbon_angle = math.degrees(math.atan2(marker_height, 2.0 * slant))
    ribbon_group = ET.SubElement(
        marker_group,
        _q("g"),
        {
            "class": "marker-annotation-ribbon",
            "data-marker": marker,
            "data-annotation": "off-ladder-no-size",
            "data-count": str(count),
            "data-marker-end-x": float_text(end_x),
            "data-ribbon-center-x": float_text(center_x),
            "data-ribbon-angle": float_text(ribbon_angle),
        },
    )
    ET.SubElement(
        ribbon_group,
        _q("polygon"),
        {
            "points": " ".join(f"{float_text(x)},{float_text(y)}" for x, y in points),
            "fill": "#F28C00",
            "stroke": "#B85F00",
            "stroke-width": "0.8",
            "class": "marker-annotation-ribbon-shape",
        },
    )
    show_text = stripe_span >= 12.5
    if show_text:
        font_size = min(7.2, max(5.0, stripe_span * 0.32))
        center_y = top_y + marker_height / 2.0
        ET.SubElement(
            ribbon_group,
            _q("text"),
            {
                "x": float_text(center_x),
                "y": float_text(center_y),
                "text-anchor": "middle",
                "dominant-baseline": "middle",
                "font-size": float_text(font_size),
                "fill": "#FFFFFF",
                "class": "marker-annotation-ribbon-text",
                "transform": (
                    "rotate("
                    f"{float_text(ribbon_angle)} {float_text(center_x)} "
                    f"{float_text(center_y)})"
                ),
            },
        ).text = "OL"


def _merge_intervals(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    merged: list[tuple[float, float]] = []
    for left, right in sorted(intervals):
        if not merged or left > merged[-1][1]:
            merged.append((left, right))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], right))
    return merged


def _segment_intersects_rect(
    segment: tuple[float, float, float, float],
    rect: tuple[float, float, float, float],
) -> bool:
    """Return whether a straight connector intersects a tick-label rectangle."""

    x1, y1, x2, y2 = segment
    left, top, right, bottom = rect
    if max(x1, x2) < left or min(x1, x2) > right or max(y1, y2) < top or min(y1, y2) > bottom:
        return False
    if y2 == y1:
        return top <= y1 <= bottom and not (max(x1, x2) < left or min(x1, x2) > right)
    for y in (top, bottom):
        t = (y - y1) / (y2 - y1)
        if 0 <= t <= 1:
            x = x1 + t * (x2 - x1)
            if left <= x <= right:
                return True
    for x in (left, right):
        if x2 == x1:
            if x == x1 and not (max(y1, y2) < top or min(y1, y2) > bottom):
                return True
            continue
        t = (x - x1) / (x2 - x1)
        if 0 <= t <= 1:
            y = y1 + t * (y2 - y1)
            if top <= y <= bottom:
                return True
    return left <= x1 <= right and top <= y1 <= bottom


def _validate_positioned_sample(positioned: PositionedSample, kit: KitDefinition) -> None:
    validate_xml_text(positioned.sample_id, "sample_id")
    if not positioned.sample_id:
        raise SvgRenderError("sample_id must not be empty.")
    known_dyes = {channel.code for channel in kit.channels}
    for peak in positioned.peaks:
        validate_xml_text(peak.marker, "marker")
        validate_xml_text(peak.allele, "allele")
        if peak.source_dye is not None:
            validate_xml_text(peak.source_dye, "source_dye")
        if peak.dye not in known_dyes:
            raise SvgRenderError(f"Peak {peak.marker} uses unknown dye {peak.dye!r}.")
        canonical_marker = kit.canonical_marker(peak.marker)
        if canonical_marker is None:
            raise SvgRenderError(f"Peak uses marker not defined for {kit.name}: {peak.marker!r}.")
        expected_dye = kit.marker(canonical_marker).dye
        if peak.dye != expected_dye:
            raise SvgRenderError(
                f"Peak {peak.marker} uses dye {peak.dye!r}; {expected_dye!r} is required."
            )
        if positioned.height_mode is PeakHeightMode.RFU:
            try:
                validate_rfu(peak.height, allow_zero=True)
            except ValueError as exc:
                raise SvgRenderError(
                    f"Peak {peak.marker} {peak.allele} has invalid RFU height {peak.height!r}."
                ) from exc
        elif peak.height is not None:
            raise SvgRenderError(
                f"Peak {peak.marker} {peak.allele} must not contain RFU data in uniform mode."
            )
        for value, name in (
            (peak.marker_range_min_bp, "marker range minimum"),
            (peak.marker_range_max_bp, "marker range maximum"),
        ):
            if not value.is_finite():
                raise SvgRenderError(f"Peak {peak.marker} has a non-finite {name}.")
        if peak.marker_range_min_bp >= peak.marker_range_max_bp:
            raise SvgRenderError(f"Peak {peak.marker} has an invalid marker range.")
        if peak.coordinate_bp is not None:
            if peak.coordinate_source is PeakCoordinateSource.UNPOSITIONED:
                raise SvgRenderError(
                    f"Peak {peak.marker} {peak.allele} has a coordinate but is marked unpositioned."
                )
            if not peak.coordinate_bp.is_finite():
                raise SvgRenderError(
                    f"Peak {peak.marker} {peak.allele} has a non-finite coordinate."
                )
            if not (peak.marker_range_min_bp <= peak.coordinate_bp <= peak.marker_range_max_bp):
                raise SvgRenderError(
                    f"Peak {peak.marker} {peak.allele} lies outside its marker range."
                )
        elif peak.coordinate_source is not PeakCoordinateSource.UNPOSITIONED:
            raise SvgRenderError(
                f"Peak {peak.marker} {peak.allele} has no coordinate but is marked "
                f"{peak.coordinate_source.value!r}."
            )


def _q(name: str) -> str:
    return f"{{{_SVG_NS}}}{name}"


def _add_style(root: ET.Element, font_family: str) -> None:
    style = ET.SubElement(root, _q("style"), {"type": "text/css"})
    style.text = f"""
text {{ font-family: {font_family}; }}
.document-title {{ font-size: {_TYPOGRAPHY_METRICS.document_title_font_size_px:g}px; font-weight: 700; fill: {_TYPOGRAPHY_METRICS.primary_text_color}; }}
.document-subtitle {{ font-size: {_TYPOGRAPHY_METRICS.document_subtitle_font_size_px:g}px; fill: {_TYPOGRAPHY_METRICS.primary_text_color}; }}
.panel-background {{ fill: #FFFFFF; stroke: #DADCE0; stroke-width: 0.9; }}
.channel-label {{ font-size: 13px; font-weight: 700; }}
.marker-label {{ font-size: {_MARKER_LABEL_METRICS.font_size_px:g}px; font-weight: 700; }}
.marker-annotation-ribbon-text {{ font-weight: 700; }}
.legend-heading {{ font-size: 9.5px; font-weight: 700; fill: #5F6368; }}
.legend-text {{ font-size: 9.5px; fill: #5F6368; }}
.legend-ribbon-swatch {{ fill: #F28C00; stroke: #B85F00; stroke-width: 0.8; }}
.horizontal-grid {{ stroke: #E6E8EB; stroke-width: 0.7; }}
.vertical-grid {{ stroke: #ECEFF1; stroke-width: 0.7; }}
.tick-line {{ stroke: #DADCE0; stroke-width: 0.7; }}
.axis-line {{ stroke-width: 1.2; }}
.axis-label, .axis-unit, .rfu-label {{ font-size: {_TYPOGRAPHY_METRICS.axis_text_font_size_px:g}px; fill: {_TYPOGRAPHY_METRICS.secondary_text_color}; }}
.peak-label {{ font-size: {_LABEL_METRICS.allele_font_size_px:g}px; font-weight: 600; }}
.height-label {{ font-size: {_LABEL_METRICS.height_font_size_px:g}px; font-weight: 400; }}
.empty-channel {{ font-size: 11px; font-style: italic; fill: #8A8D91; }}
.disclaimer {{ font-size: 9.5px; fill: #5F6368; }}
.warning {{ font-size: 9.5px; font-weight: 700; fill: #A15C00; }}
""".strip()
