from __future__ import annotations

import builtins
import tempfile
import unittest
from importlib.util import find_spec
from pathlib import Path
from unittest.mock import patch

from epg_renderer import (
    load_project,
    render_file,
    render_svg,
)
from epg_renderer.render_io import output_format_from_path, write_epg_output, write_raster_image
from epg_renderer.render_options import (
    OutputFormat,
    RasterDependencyError,
    RasterRenderError,
    RasterRenderOptions,
    SvgRenderError,
)

RASTER_DEPENDENCIES_AVAILABLE = find_spec("cairosvg") is not None and find_spec("PIL") is not None

FIXTURES = Path(__file__).with_name("fixtures")


class RasterOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sample = load_project(FIXTURES / "globalfiler_minimal.tsv").sample("S1")
        cls.svg = render_svg(sample)

    def test_output_format_is_inferred_case_insensitively(self):
        self.assertIs(output_format_from_path("x.SVG"), OutputFormat.SVG)
        self.assertIs(output_format_from_path("x.PNG"), OutputFormat.PNG)
        self.assertIs(output_format_from_path("x.JPG"), OutputFormat.JPEG)
        self.assertIs(output_format_from_path("x.jpeg"), OutputFormat.JPEG)

    def test_unsupported_suffix_is_rejected(self):
        with self.assertRaises(SvgRenderError):
            output_format_from_path("x.pdf")

    @unittest.skipUnless(RASTER_DEPENDENCIES_AVAILABLE, "Raster dependencies are not installed")
    def test_png_output_is_valid_and_scaled(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "image.png"
            write_raster_image(self.svg, target, options=RasterRenderOptions(scale=0.5))
            with Image.open(target) as image:
                self.assertEqual(image.format, "PNG")
                self.assertEqual(image.size, (800, 691))

    @unittest.skipUnless(RASTER_DEPENDENCIES_AVAILABLE, "Raster dependencies are not installed")
    def test_jpg_and_jpeg_outputs_are_valid_rgb_images(self):
        from PIL import Image

        for suffix in ("jpg", "jpeg"):
            with self.subTest(suffix=suffix), tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / f"image.{suffix}"
                write_raster_image(self.svg, target, options=RasterRenderOptions(scale=0.5))
                with Image.open(target) as image:
                    self.assertEqual(image.format, "JPEG")
                    self.assertEqual(image.mode, "RGB")
                    self.assertEqual(image.size, (800, 691))

    @unittest.skipUnless(RASTER_DEPENDENCIES_AVAILABLE, "Raster dependencies are not installed")
    def test_end_to_end_png_and_jpg_selection_by_suffix(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as directory:
            for suffix, expected_format in (("png", "PNG"), ("jpg", "JPEG")):
                target = Path(directory) / f"out.{suffix}"
                result = render_file(
                    FIXTURES / "globalfiler_minimal.tsv",
                    target,
                    raster_options=RasterRenderOptions(scale=0.25),
                )
                self.assertEqual(result, target)
                with Image.open(target) as image:
                    self.assertEqual(image.format, expected_format)

    @unittest.skipUnless(RASTER_DEPENDENCIES_AVAILABLE, "Raster dependencies are not installed")
    def test_raster_writes_are_atomic_and_leave_no_temp_files(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "image.png"
            target.write_bytes(b"old")
            write_raster_image(self.svg, target, options=RasterRenderOptions(scale=0.25))
            self.assertTrue(target.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertEqual(list(Path(directory).glob(".*.tmp")), [])

    def test_write_epg_output_dispatches_svg_without_rasterization(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "image.svg"
            with patch(
                "epg_renderer.render_io._load_raster_dependencies", side_effect=AssertionError
            ):
                write_epg_output(self.svg, target)
            self.assertTrue(target.read_text(encoding="utf-8").startswith("<?xml"))

    def test_missing_dependency_error_points_to_the_installation_guide(self):
        # Until 0.14.0.dev11 the message said "pip install epg-renderer[raster]": the
        # PyPI name is not ours, and GUI users without a terminal cannot act on it.
        original_import = builtins.__import__

        def blocked_import(name, *args, **kwargs):
            if name == "cairosvg":
                raise ImportError("blocked for test")
            return original_import(name, *args, **kwargs)

        with (
            tempfile.TemporaryDirectory() as directory,
            patch("builtins.__import__", side_effect=blocked_import),
            self.assertRaises(RasterDependencyError) as caught,
        ):
            write_raster_image(self.svg, Path(directory) / "image.png")
        message = str(caught.exception)
        for phrase in (
            "CairoSVG",
            "Pillow",
            "https://github.com/rsivth/EPG-Renderer/blob/main/docs/INSTALLATION.md"
            "#png-and-jpg-output",
            "SVG output",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, message)
        self.assertNotIn("pip install", message)

    def test_missing_native_cairo_library_has_the_actionable_error(self):
        # Until 0.14.0.dev15 only ImportError was translated. With CairoSVG installed but
        # the native Cairo library missing, importing CairoSVG raises OSError, which
        # reached the GUI as "Could not create image" with a technical message.
        original_import = builtins.__import__

        def blocked_import(name, *args, **kwargs):
            if name == "cairosvg":
                raise OSError("no library called 'cairo-2' was found")
            return original_import(name, *args, **kwargs)

        with (
            tempfile.TemporaryDirectory() as directory,
            patch("builtins.__import__", side_effect=blocked_import),
            self.assertRaises(RasterDependencyError) as caught,
        ):
            write_raster_image(self.svg, Path(directory) / "image.png")
        message = str(caught.exception)
        for phrase in (
            "native Cairo library",
            "SVG output",
            "https://github.com/rsivth/EPG-Renderer/blob/main/docs/INSTALLATION.md"
            "#png-and-jpg-output",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, message)
        self.assertNotIn("not installed", message)

    def test_invalid_raster_options_are_rejected(self):
        invalid = (
            RasterRenderOptions(scale=0),
            RasterRenderOptions(scale=11),
            RasterRenderOptions(jpeg_quality=0),
            RasterRenderOptions(jpeg_quality=101),
        )
        with tempfile.TemporaryDirectory() as directory:
            for options in invalid:
                with self.subTest(options=options), self.assertRaises(RasterRenderError):
                    write_raster_image(self.svg, Path(directory) / "image.png", options=options)

    def test_raster_writer_rejects_svg_suffix(self):
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(RasterRenderError):
            write_raster_image(self.svg, Path(directory) / "image.svg")


if __name__ == "__main__":
    unittest.main()
