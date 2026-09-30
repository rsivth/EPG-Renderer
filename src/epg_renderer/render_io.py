"""Output-format dispatch, validation, rasterization and atomic file writing."""

from __future__ import annotations

import os
import tempfile
import xml.etree.ElementTree as ET
from contextlib import suppress
from io import BytesIO
from pathlib import Path
from types import TracebackType
from typing import Protocol, cast

from .render_options import (
    OutputFormat,
    RasterDependencyError,
    RasterRenderError,
    RasterRenderOptions,
    SvgRenderError,
    validate_raster_options,
)

_SVG_TAG = "{http://www.w3.org/2000/svg}svg"


class _CairoSvgModule(Protocol):
    """Structural interface required from CairoSVG."""

    def svg2png(
        self,
        *,
        bytestring: bytes,
        output_width: int,
        output_height: int,
    ) -> bytes:
        """Convert SVG bytes to PNG bytes at the requested dimensions."""
        ...


class _RasterImage(Protocol):
    """Structural image interface required from Pillow."""

    def __enter__(self) -> _RasterImage:
        """Enter the image resource context."""
        ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        """Close the image resource when leaving its context."""
        ...

    def convert(self, mode: str) -> _RasterImage:
        """Return an image converted to the requested pixel mode."""
        ...

    def save(
        self,
        fp: BytesIO,
        *,
        format: str,
        quality: int,
        optimize: bool,
        progressive: bool,
        subsampling: int,
    ) -> None:
        """Encode the image into the supplied binary stream."""
        ...


class _ImageModule(Protocol):
    """Structural module interface required from Pillow."""

    def open(self, fp: BytesIO) -> _RasterImage:
        """Open an image from an in-memory binary stream."""
        ...


def output_format_from_path(output_path: str | Path) -> OutputFormat:
    """Return the supported output format encoded by a file suffix."""

    suffix = Path(output_path).suffix.casefold()
    if suffix == ".svg":
        return OutputFormat.SVG
    if suffix == ".png":
        return OutputFormat.PNG
    if suffix in {".jpg", ".jpeg"}:
        return OutputFormat.JPEG
    raise SvgRenderError("Unsupported output suffix. Use .svg, .png, .jpg or .jpeg.")


def write_epg_output(
    svg: str,
    output_path: str | Path,
    *,
    raster_options: RasterRenderOptions | None = None,
) -> Path:
    """Write a rendered SVG document in the format selected by ``output_path``."""

    output_format = output_format_from_path(output_path)
    if output_format is OutputFormat.SVG:
        if raster_options is not None:
            validate_raster_options(raster_options)
        return write_svg(svg, output_path)
    return write_raster_image(svg, output_path, options=raster_options)


def write_svg(svg: str, output_path: str | Path) -> Path:
    """Atomically write a complete SVG document as UTF-8."""

    path = Path(output_path)
    if output_format_from_path(path) is not OutputFormat.SVG:
        raise SvgRenderError("SVG output paths must use the .svg suffix.")
    _validate_svg_document(svg)
    return _atomic_write_text(path, svg)


def write_raster_image(
    svg: str,
    output_path: str | Path,
    *,
    options: RasterRenderOptions | None = None,
) -> Path:
    """Rasterize a generated SVG and atomically write PNG or JPEG output.

    CairoSVG is used for SVG rasterization. JPEG encoding is performed with Pillow.
    Both are optional dependencies from the package's ``raster`` extra.
    """

    path = Path(output_path)
    output_format = output_format_from_path(path)
    if output_format is OutputFormat.SVG:
        raise RasterRenderError("Raster output paths must use .png, .jpg or .jpeg.")
    _validate_svg_document(svg)
    opts = validate_raster_options(options or RasterRenderOptions())
    cairosvg, image_module = _load_raster_dependencies()

    try:
        root = ET.fromstring(svg)
        width = int(root.attrib["width"])
        height = int(root.attrib["height"])
    except (ET.ParseError, KeyError, TypeError, ValueError) as exc:
        raise RasterRenderError("SVG width and height must be integer pixel values.") from exc

    try:
        png_bytes = cairosvg.svg2png(
            bytestring=svg.encode("utf-8"),
            output_width=max(1, round(width * opts.scale)),
            output_height=max(1, round(height * opts.scale)),
        )
    except Exception as exc:
        raise RasterRenderError(f"Could not rasterize SVG: {exc}") from exc
    if not isinstance(png_bytes, bytes):
        raise RasterRenderError("CairoSVG did not return PNG bytes.")

    if output_format is OutputFormat.PNG:
        return _atomic_write_bytes(path, png_bytes)

    try:
        with image_module.open(BytesIO(png_bytes)) as image:
            rgb = image.convert("RGB")
            buffer = BytesIO()
            rgb.save(
                buffer,
                format="JPEG",
                quality=opts.jpeg_quality,
                optimize=opts.jpeg_optimize,
                progressive=False,
                subsampling=0,
            )
            jpeg_bytes = buffer.getvalue()
    except Exception as exc:
        raise RasterRenderError(f"Could not encode JPEG output: {exc}") from exc
    return _atomic_write_bytes(path, jpeg_bytes)


def _load_raster_dependencies() -> tuple[_CairoSvgModule, _ImageModule]:
    try:
        import cairosvg
        from PIL import Image
    except ImportError as exc:
        raise RasterDependencyError(
            "PNG/JPEG output requires CairoSVG and Pillow, which are not installed. "
            "SVG output works without them. Installation: "
            "https://github.com/rsivth/EPG-Renderer/blob/main/docs/INSTALLATION.md"
            "#png-and-jpg-output"
        ) from exc
    return cast(_CairoSvgModule, cairosvg), cast(_ImageModule, Image)


def _validate_svg_document(svg: str) -> None:
    if not svg.startswith('<?xml version="1.0" encoding="UTF-8"?>'):
        raise SvgRenderError("The supplied text is not a complete EPG-Renderer SVG document.")
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as exc:
        raise SvgRenderError("The supplied SVG is not well-formed XML.") from exc
    if root.tag != _SVG_TAG or root.attrib.get("data-epg-renderer-version") is None:
        raise SvgRenderError("The supplied SVG is not an EPG-Renderer document.")


def _atomic_write_text(path: Path, text: str) -> Path:
    return _atomic_write_bytes(path, text.encode("utf-8"), error=SvgRenderError)


def _atomic_write_bytes(
    path: Path,
    data: bytes,
    *,
    error: type[SvgRenderError] = RasterRenderError,
) -> Path:
    temp_name: str | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as handle:
            temp_name = handle.name
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except OSError as exc:
        raise error(f"Could not write output to {path}: {exc}") from exc
    finally:
        if temp_name:
            with suppress(OSError):
                Path(temp_name).unlink(missing_ok=True)
    return path
