"""Shared immutable geometry metrics for peak-label layout and rendering."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil


@dataclass(frozen=True, slots=True)
class _LabelLayoutParameters:
    allele_font_size_px: float
    height_font_size_px: float
    horizontal_padding_px: float
    minimum_width_px: float
    horizontal_gap_px: float
    lane_gap_px: int
    top_padding_px: int
    line_gap_px: int
    bottom_padding_px: int
    box_top_offset_px: int
    label_area_bottom_padding_px: int
    signal_top_offset_px: int
    minimum_signal_height_px: int


@dataclass(frozen=True, slots=True)
class _LabelMetrics:
    allele_font_size_px: float
    height_font_size_px: float
    horizontal_padding_px: float
    minimum_width_px: float
    horizontal_gap_px: float
    lane_height_px: int
    rfu_box_height_px: int
    uniform_box_height_px: int
    box_top_offset_px: int
    allele_baseline_offset_px: int
    height_line_offset_px: int
    label_area_bottom_padding_px: int
    signal_top_offset_px: int
    minimum_signal_height_px: int


def _build_label_metrics(params: _LabelLayoutParameters) -> _LabelMetrics:
    allele_baseline_offset_px = params.top_padding_px + ceil(params.allele_font_size_px - 0.5)
    height_line_offset_px = params.line_gap_px + ceil(params.height_font_size_px)
    uniform_box_height_px = allele_baseline_offset_px + params.bottom_padding_px + 1
    rfu_box_height_px = (
        allele_baseline_offset_px + height_line_offset_px + params.bottom_padding_px + 1
    )
    lane_height_px = rfu_box_height_px + params.lane_gap_px
    return _LabelMetrics(
        allele_font_size_px=params.allele_font_size_px,
        height_font_size_px=params.height_font_size_px,
        horizontal_padding_px=params.horizontal_padding_px,
        minimum_width_px=params.minimum_width_px,
        horizontal_gap_px=params.horizontal_gap_px,
        lane_height_px=lane_height_px,
        rfu_box_height_px=rfu_box_height_px,
        uniform_box_height_px=uniform_box_height_px,
        box_top_offset_px=params.box_top_offset_px,
        allele_baseline_offset_px=allele_baseline_offset_px,
        height_line_offset_px=height_line_offset_px,
        label_area_bottom_padding_px=params.label_area_bottom_padding_px,
        signal_top_offset_px=params.signal_top_offset_px,
        minimum_signal_height_px=params.minimum_signal_height_px,
    )


_LABEL_LAYOUT_PARAMETERS = _LabelLayoutParameters(
    allele_font_size_px=11.5,
    height_font_size_px=10.0,
    horizontal_padding_px=12.0,
    minimum_width_px=18.0,
    horizontal_gap_px=3.0,
    lane_gap_px=3,
    top_padding_px=1,
    line_gap_px=1,
    bottom_padding_px=5,
    box_top_offset_px=18,
    label_area_bottom_padding_px=26,
    signal_top_offset_px=48,
    minimum_signal_height_px=45,
)

_LABEL_METRICS = _build_label_metrics(_LABEL_LAYOUT_PARAMETERS)


def _minimum_channel_height(label_lanes: int) -> int:
    return (
        _LABEL_METRICS.signal_top_offset_px
        + _LABEL_METRICS.minimum_signal_height_px
        + _LABEL_METRICS.label_area_bottom_padding_px
        + label_lanes * _LABEL_METRICS.lane_height_px
    )


@dataclass(frozen=True, slots=True)
class _MarkerLabelMetrics:
    font_size_px: float
    fallback_font_size_px: float
    band_height_px: int
    horizontal_padding_px: float
    minimum_available_width_px: float
    baseline_offset_px: int


_MARKER_LABEL_METRICS = _MarkerLabelMetrics(
    font_size_px=11.5,
    fallback_font_size_px=8.4,
    band_height_px=18,
    horizontal_padding_px=6.0,
    minimum_available_width_px=8.0,
    baseline_offset_px=13,
)


@dataclass(frozen=True, slots=True)
class _TypographyMetrics:
    document_title_font_size_px: float
    document_subtitle_font_size_px: float
    axis_text_font_size_px: float
    primary_text_color: str
    secondary_text_color: str


_TYPOGRAPHY_METRICS = _TypographyMetrics(
    document_title_font_size_px=20.0,
    document_subtitle_font_size_px=11.0,
    axis_text_font_size_px=10.0,
    primary_text_color="#202124",
    secondary_text_color="#5F6368",
)


@dataclass(frozen=True, slots=True)
class _FooterMetrics:
    """Vertical footer layout below the last channel panel, in pixels."""

    first_baseline_offset_px: int
    disclaimer_line_gap_px: int
    disclaimer_block_px: int
    legend_gap_px: int
    legend_heading_px: int
    legend_line_px: int
    bottom_padding_px: int


_FOOTER_METRICS = _FooterMetrics(
    first_baseline_offset_px=24,
    disclaimer_line_gap_px=17,
    disclaimer_block_px=28,
    legend_gap_px=14,
    legend_heading_px=22,
    legend_line_px=16,
    bottom_padding_px=17,
)


def _minimum_footer_height_with_disclaimer() -> int:
    return (
        _FOOTER_METRICS.first_baseline_offset_px
        + _FOOTER_METRICS.disclaimer_line_gap_px
        + _FOOTER_METRICS.bottom_padding_px
    )
