"""Pure layout calculations used by the SVG renderer."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal

from .domain import PeakHeightMode
from .kits import DyeChannel
from .positions import MarkerCoordinateDefinition, PositionedPeak
from .render_metrics import _LABEL_METRICS
from .render_options import RfuScaleMode, SvgRenderError, _ValidatedOptions


@dataclass(frozen=True, slots=True)
class LabelPlacement:
    """Horizontal label position and allocated vertical lane."""

    x: float
    lane: int
    width: float


@dataclass(frozen=True, slots=True)
class ChannelPlan:
    """Precomputed label layout and resulting panel height for one channel."""

    placements: tuple[LabelPlacement, ...]
    lane_count: int
    height: int
    height_mode: PeakHeightMode = PeakHeightMode.RFU


def plan_channel_labels(
    peaks: list[PositionedPeak],
    *,
    options: _ValidatedOptions,
    height_mode: PeakHeightMode = PeakHeightMode.RFU,
    x_min: Decimal,
    x_max: Decimal,
    plot_left: float,
    plot_right: float,
) -> ChannelPlan:
    """Allocate as many vertical lanes as required to prevent label overlap."""

    if not peaks:
        return ChannelPlan(
            placements=(),
            lane_count=0,
            height=options.channel_height,
            height_mode=height_mode,
        )
    x_positions = [
        x_to_px(_required_coordinate_bp(peak), x_min, x_max, plot_left, plot_right)
        for peak in peaks
    ]
    label_widths = [
        max(
            estimate_text_width(peak.allele, _LABEL_METRICS.allele_font_size_px),
            (
                estimate_text_width(str(peak.height), _LABEL_METRICS.height_font_size_px)
                if height_mode is PeakHeightMode.RFU
                else 0.0
            ),
        )
        + _LABEL_METRICS.horizontal_padding_px
        for peak in peaks
    ]
    placements = assign_label_lanes(
        x_positions,
        label_widths,
        min_x=plot_left,
        max_x=plot_right,
    )
    lane_count = max((placement.lane for placement in placements), default=-1) + 1
    extra_lanes = max(0, lane_count - options.label_lanes)
    return ChannelPlan(
        placements=tuple(placements),
        lane_count=lane_count,
        height=options.channel_height + extra_lanes * _LABEL_METRICS.lane_height_px,
        height_mode=height_mode,
    )


def _required_coordinate_bp(peak: PositionedPeak) -> Decimal:
    if peak.coordinate_bp is None:
        raise SvgRenderError(f"Peak {peak.marker} {peak.allele!r} has no coordinate.")
    return peak.coordinate_bp


def resolve_x_domain(
    marker_definitions: Iterable[MarkerCoordinateDefinition],
    options: _ValidatedOptions,
) -> tuple[Decimal, Decimal]:
    """Resolve the explicit or kit-derived horizontal base-pair domain."""

    if options.x_min_bp is not None and options.x_max_bp is not None:
        x_min, x_max = options.x_min_bp, options.x_max_bp
    else:
        markers = tuple(marker_definitions)
        minimum = min(marker.range_min_bp for marker in markers)
        maximum = max(marker.range_max_bp for marker in markers)
        x_min = minimum - Decimal("5")
        x_max = (maximum / Decimal(10)).to_integral_value(rounding=ROUND_CEILING) * 10 + 10
    if x_max - x_min < 100:
        raise SvgRenderError("The horizontal base-pair domain is too narrow.")
    return x_min, x_max


def rfu_scale_maxima(
    channels: Iterable[DyeChannel],
    peaks_by_dye: Mapping[str, list[PositionedPeak]],
    options: _ValidatedOptions,
    *,
    height_mode: PeakHeightMode = PeakHeightMode.RFU,
) -> dict[str, int]:
    """Return the vertical scale maximum for every dye channel."""

    if height_mode is PeakHeightMode.UNIFORM:
        if options.fixed_max_rfu is not None:
            raise SvgRenderError("fixed_max_rfu cannot be used with uniform peak heights.")
        return {channel.code: 1 for channel in channels}
    all_heights = [
        peak.height for peaks in peaks_by_dye.values() for peak in peaks if peak.height is not None
    ]
    highest = max(all_heights, default=0)
    if options.fixed_max_rfu is not None:
        if highest > options.fixed_max_rfu:
            raise SvgRenderError(
                f"fixed_max_rfu={options.fixed_max_rfu} is below the highest "
                f"called peak ({highest} RFU)."
            )
        return {channel.code: options.fixed_max_rfu for channel in channels}
    if options.rfu_scale_mode is RfuScaleMode.GLOBAL:
        axis_max = nice_rfu_max(highest)
        return {channel.code: axis_max for channel in channels}
    maxima: dict[str, int] = {}
    for channel in channels:
        value = max(
            (peak.height for peak in peaks_by_dye.get(channel.code, []) if peak.height is not None),
            default=0,
        )
        maxima[channel.code] = nice_rfu_max(value)
    return maxima


def nice_rfu_max(value: int) -> int:
    """Round a positive RFU maximum upward to a readable axis limit."""
    if value <= 0:
        return 100
    target = max(10.0, float(value))
    exponent = math.floor(math.log10(target))
    magnitude = 10**exponent
    scaled = target / magnitude
    for candidate in (1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 7.5, 8.0, 10.0):
        if scaled <= candidate:
            return int(candidate * magnitude)
    return int(10 * magnitude)


def assign_label_lanes(
    x_positions: list[float],
    widths: list[float],
    *,
    min_x: float,
    max_x: float,
) -> list[LabelPlacement]:
    """Greedily allocate unlimited non-overlapping lanes."""

    if len(x_positions) != len(widths):
        raise SvgRenderError("Label-position and width counts differ.")
    lane_right: list[float] = []
    placements: list[LabelPlacement] = []
    gap = _LABEL_METRICS.horizontal_gap_px
    for x, width in zip(x_positions, widths, strict=False):
        width = max(_LABEL_METRICS.minimum_width_px, min(width, max_x - min_x))
        centre = max(min_x + width / 2, min(max_x - width / 2, x))
        left = centre - width / 2
        right = centre + width / 2
        lane = next(
            (
                index
                for index, occupied_right in enumerate(lane_right)
                if left >= occupied_right + gap
            ),
            None,
        )
        if lane is None:
            lane = len(lane_right)
            lane_right.append(right)
        else:
            lane_right[lane] = right
        placements.append(LabelPlacement(centre, lane, width))
    return placements


def x_to_px(
    bp: Decimal,
    x_min: Decimal,
    x_max: Decimal,
    plot_left: float,
    plot_right: float,
) -> float:
    """Map a base-pair coordinate linearly onto the plot x-axis."""
    ratio = float((bp - x_min) / (x_max - x_min))
    return plot_left + ratio * (plot_right - plot_left)


def ticks(x_min: Decimal, x_max: Decimal, interval: int) -> tuple[int, ...]:
    """Return inclusive decimal tick values for a positive interval."""
    start = math.ceil(float(x_min) / interval) * interval
    end = math.floor(float(x_max) / interval) * interval
    return tuple(range(start, end + 1, interval))


def estimate_text_width(text: str, font_size: float) -> float:
    """Estimate rendered text width using deterministic font-independent factors."""
    return _estimate_text_width(text, font_size, base_factor=0.54, wide_factor=0.18)


def _estimate_bold_text_width(text: str, font_size: float) -> float:
    """Estimate bold sans-serif text conservatively for marker-band fitting."""
    return _estimate_text_width(text, font_size, base_factor=0.56, wide_factor=0.40)


def _estimate_text_width(
    text: str,
    font_size: float,
    *,
    base_factor: float,
    wide_factor: float,
) -> float:
    """Apply deterministic per-character factors for one text style."""
    wide = sum(character in "MW@%" for character in text)
    narrow = sum(character in "1ilI.,'" for character in text)
    base = len(text) * font_size * base_factor
    return max(
        font_size,
        base + wide * font_size * wide_factor - narrow * font_size * 0.16,
    )


def decimal_text(value: Decimal) -> str:
    """Serialize a decimal without exponent notation or insignificant zeros."""
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def float_text(value: float) -> str:
    """Serialize a float compactly for deterministic SVG attributes."""
    return f"{value:.3f}".rstrip("0").rstrip(".")
