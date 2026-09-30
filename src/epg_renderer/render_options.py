"""Renderer option types and validation.

This module contains no SVG construction or file-system code.  It converts the public
option dataclasses into immutable validated values shared by layout and rendering.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal, DecimalException
from enum import Enum

from .render_metrics import _minimum_channel_height, _minimum_footer_height_with_disclaimer


class SvgRenderError(ValueError):
    """Base exception for invalid render requests."""


class UnpositionedPeakRenderError(SvgRenderError):
    """Raised when a peak without a nominal x-coordinate must be rendered."""


class SampleSelectionError(SvgRenderError):
    """Raised when a project sample cannot be selected unambiguously."""


class RasterRenderError(SvgRenderError):
    """Raised when PNG/JPEG output cannot be produced."""


class RasterDependencyError(RasterRenderError):
    """Raised when optional raster dependencies are unavailable."""


class OutputFormat(str, Enum):
    """Supported file formats inferred from the output-path suffix."""

    SVG = "svg"
    PNG = "png"
    JPEG = "jpeg"


class RfuScaleMode(str, Enum):
    """How RFU axes are scaled across dye-channel panels."""

    PER_CHANNEL = "per_channel"
    GLOBAL = "global"


class UnpositionedPolicy(str, Enum):
    """How peaks without a nominal coordinate are handled."""

    ERROR = "error"
    OMIT = "omit"


class YellowChannelMode(str, Enum):
    """Display color used for channels declared as yellow by the kit definition."""

    YELLOW = "yellow"
    BLACK = "black"


@dataclass(frozen=True, slots=True)
class SvgRenderOptions:
    """Layout and scaling options for a deterministic SVG document."""

    width: int = 1600
    channel_height: int = 250
    header_height: int = 74
    footer_height: int = 58
    left_margin: int = 92
    right_margin: int = 28
    x_min_bp: Decimal | int | float | str | None = None
    x_max_bp: Decimal | int | float | str | None = None
    x_tick_interval_bp: int = 50
    rfu_scale_mode: RfuScaleMode | str = RfuScaleMode.PER_CHANNEL
    fixed_max_rfu: int | None = None
    unpositioned_policy: UnpositionedPolicy | str = UnpositionedPolicy.ERROR
    yellow_channel_mode: YellowChannelMode | str = YellowChannelMode.YELLOW
    label_lanes: int = 4
    peak_half_width_bp: Decimal | int | float | str = Decimal("0.8")
    show_grid: bool = True
    show_marker_bands: bool = True
    show_disclaimer: bool = True
    title: str | None = None
    font_family: str = "Arial, Helvetica, sans-serif"


@dataclass(frozen=True, slots=True)
class RasterRenderOptions:
    """Options used when rasterizing the generated SVG."""

    scale: float = 2.0
    jpeg_quality: int = 95
    jpeg_optimize: bool = True


@dataclass(frozen=True, slots=True)
class _ValidatedRasterOptions:
    scale: float
    jpeg_quality: int
    jpeg_optimize: bool


@dataclass(frozen=True, slots=True)
class _ValidatedOptions:
    width: int
    channel_height: int
    header_height: int
    footer_height: int
    left_margin: int
    right_margin: int
    x_min_bp: Decimal | None
    x_max_bp: Decimal | None
    x_tick_interval_bp: int
    rfu_scale_mode: RfuScaleMode
    fixed_max_rfu: int | None
    unpositioned_policy: UnpositionedPolicy
    yellow_channel_mode: YellowChannelMode
    label_lanes: int
    peak_half_width_bp: Decimal
    show_grid: bool
    show_marker_bands: bool
    show_disclaimer: bool
    title: str | None
    font_family: str


def validate_svg_options(options: SvgRenderOptions) -> _ValidatedOptions:
    """Validate public SVG options and return their normalized internal form."""

    _validate_integer_options(options)
    _validate_canvas(options)
    _validate_label_area(options)
    _validate_boolean_options(options)
    _validate_footer(options)
    fixed_max_rfu = _validated_fixed_max_rfu(options.fixed_max_rfu)
    scale_mode, unpositioned, yellow_channel_mode = _validated_modes(options)
    x_min, x_max = _validated_x_domain(options)
    peak_half_width = _validated_peak_half_width(options.peak_half_width_bp)
    font_family = _validated_font_family(options.font_family)
    title = _validated_title(options.title)
    return _ValidatedOptions(
        width=options.width,
        channel_height=options.channel_height,
        header_height=options.header_height,
        footer_height=options.footer_height,
        left_margin=options.left_margin,
        right_margin=options.right_margin,
        x_min_bp=x_min,
        x_max_bp=x_max,
        x_tick_interval_bp=options.x_tick_interval_bp,
        rfu_scale_mode=scale_mode,
        fixed_max_rfu=fixed_max_rfu,
        unpositioned_policy=unpositioned,
        yellow_channel_mode=yellow_channel_mode,
        label_lanes=options.label_lanes,
        peak_half_width_bp=peak_half_width,
        show_grid=options.show_grid,
        show_marker_bands=options.show_marker_bands,
        show_disclaimer=options.show_disclaimer,
        title=title,
        font_family=font_family,
    )


def _validate_integer_options(options: SvgRenderOptions) -> None:
    integer_fields = {
        "width": options.width,
        "channel_height": options.channel_height,
        "header_height": options.header_height,
        "footer_height": options.footer_height,
        "left_margin": options.left_margin,
        "right_margin": options.right_margin,
        "x_tick_interval_bp": options.x_tick_interval_bp,
        "label_lanes": options.label_lanes,
    }
    for name, value in integer_fields.items():
        if isinstance(value, bool) or not isinstance(value, int):
            raise SvgRenderError(f"{name} must be an integer.")


def _validate_canvas(options: SvgRenderOptions) -> None:
    if options.width < 700:
        raise SvgRenderError("width must be at least 700 pixels.")
    if options.channel_height < 220:
        raise SvgRenderError("channel_height must be at least 220 pixels.")
    if options.header_height < 55 or options.footer_height < 30:
        raise SvgRenderError("Header or footer height is too small.")
    if options.left_margin < 65 or options.right_margin < 10:
        raise SvgRenderError("Plot margins are too small.")
    if options.left_margin + options.right_margin >= options.width - 400:
        raise SvgRenderError("Margins leave insufficient horizontal plot space.")
    if options.x_tick_interval_bp <= 0:
        raise SvgRenderError("x_tick_interval_bp must be positive.")


def _validate_label_area(options: SvgRenderOptions) -> None:
    if options.label_lanes < 1 or options.label_lanes > 8:
        raise SvgRenderError("label_lanes must be between 1 and 8.")
    minimum_channel_height = _minimum_channel_height(options.label_lanes)
    if options.channel_height < minimum_channel_height:
        raise SvgRenderError(
            f"channel_height must be at least {minimum_channel_height} pixels for "
            f"{options.label_lanes} label lanes."
        )


def _validate_boolean_options(options: SvgRenderOptions) -> None:
    boolean_fields = {
        "show_grid": options.show_grid,
        "show_marker_bands": options.show_marker_bands,
        "show_disclaimer": options.show_disclaimer,
    }
    for name, value in boolean_fields.items():
        if not isinstance(value, bool):
            raise SvgRenderError(f"{name} must be boolean.")


def _validate_footer(options: SvgRenderOptions) -> None:
    minimum = _minimum_footer_height_with_disclaimer()
    if options.show_disclaimer and options.footer_height < minimum:
        raise SvgRenderError(
            f"footer_height must be at least {minimum} pixels when the disclaimer is shown."
        )


def _validated_fixed_max_rfu(value: int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise SvgRenderError("fixed_max_rfu must be an integer or None.")
    if value <= 0:
        raise SvgRenderError("fixed_max_rfu must be positive.")
    return value


def _validated_modes(
    options: SvgRenderOptions,
) -> tuple[RfuScaleMode, UnpositionedPolicy, YellowChannelMode]:
    try:
        scale_mode = RfuScaleMode(options.rfu_scale_mode)
    except ValueError as exc:
        raise SvgRenderError(f"Unknown RFU scale mode: {options.rfu_scale_mode!r}.") from exc
    try:
        unpositioned = UnpositionedPolicy(options.unpositioned_policy)
    except ValueError as exc:
        raise SvgRenderError(
            f"Unknown unpositioned-peak policy: {options.unpositioned_policy!r}."
        ) from exc
    try:
        yellow_channel_mode = YellowChannelMode(options.yellow_channel_mode)
    except ValueError as exc:
        raise SvgRenderError(
            f"Unknown yellow-channel mode: {options.yellow_channel_mode!r}."
        ) from exc
    return scale_mode, unpositioned, yellow_channel_mode


def _validated_x_domain(options: SvgRenderOptions) -> tuple[Decimal | None, Decimal | None]:
    x_min = optional_decimal(options.x_min_bp, "x_min_bp")
    x_max = optional_decimal(options.x_max_bp, "x_max_bp")
    if (x_min is None) != (x_max is None):
        raise SvgRenderError("x_min_bp and x_max_bp must be supplied together.")
    if x_min is not None and x_max is not None and x_min >= x_max:
        raise SvgRenderError("x_min_bp must be smaller than x_max_bp.")
    return x_min, x_max


def _validated_peak_half_width(value: Decimal | int | float | str) -> Decimal:
    peak_half_width = required_decimal(value, "peak_half_width_bp")
    if peak_half_width <= 0 or peak_half_width > 10:
        raise SvgRenderError("peak_half_width_bp must be greater than 0 and at most 10.")
    return peak_half_width


def _validated_font_family(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SvgRenderError("font_family must be a non-empty string.")
    validate_xml_text(value, "font_family")
    allowed_font_punctuation = set(" _.,'\"-")
    if any(
        not (character.isalnum() or character in allowed_font_punctuation) for character in value
    ):
        raise SvgRenderError("font_family contains unsafe CSS characters.")
    return value.strip()


def _validated_title(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SvgRenderError("title must be a string or None.")
    validate_xml_text(value, "title")
    return value


def validate_raster_options(options: RasterRenderOptions) -> _ValidatedRasterOptions:
    """Validate and normalize rasterization options."""

    if isinstance(options.scale, bool) or not isinstance(options.scale, int | float):
        raise RasterRenderError("scale must be a finite number.")
    scale = float(options.scale)
    if not math.isfinite(scale) or not 0.1 <= scale <= 10.0:
        raise RasterRenderError("scale must be between 0.1 and 10.0.")
    if isinstance(options.jpeg_quality, bool) or not isinstance(options.jpeg_quality, int):
        raise RasterRenderError("jpeg_quality must be an integer.")
    if not 1 <= options.jpeg_quality <= 100:
        raise RasterRenderError("jpeg_quality must be between 1 and 100.")
    if not isinstance(options.jpeg_optimize, bool):
        raise RasterRenderError("jpeg_optimize must be a boolean.")
    return _ValidatedRasterOptions(scale, options.jpeg_quality, options.jpeg_optimize)


def validate_xml_text(value: str, field: str) -> None:
    """Reject characters forbidden by XML 1.0."""

    for character in value:
        code = ord(character)
        permitted = (
            code in (0x9, 0xA, 0xD)
            or 0x20 <= code <= 0xD7FF
            or 0xE000 <= code <= 0xFFFD
            or 0x10000 <= code <= 0x10FFFF
        )
        if not permitted:
            raise SvgRenderError(f"{field} contains a character not permitted in XML 1.0.")


def required_decimal(value: Decimal | int | float | str, name: str) -> Decimal:
    """Parse a finite decimal option and reject missing values."""
    try:
        result = Decimal(str(value))
    except (DecimalException, ValueError) as exc:
        raise SvgRenderError(f"{name} must be a finite number.") from exc
    if not result.is_finite():
        raise SvgRenderError(f"{name} must be a finite number.")
    return result


def optional_decimal(
    value: Decimal | int | float | str | None,
    name: str,
) -> Decimal | None:
    """Parse an optional finite decimal option."""
    if value is None:
        return None
    return required_decimal(value, name)
