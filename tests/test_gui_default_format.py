"""Regressions for the preselected image format in the main GUI window.

Until 0.14.0.dev13 the GUI always preselected SVG, although the guide recommends PNG or
JPG for slides and the Windows program always includes PNG and JPG support. Since
0.14.0.dev14 PNG is preselected when raster output works and SVG otherwise. Raster
output does not work when CairoSVG or Pillow is missing, and also when CairoSVG is
installed but the native Cairo library is not: importing CairoSVG then raises OSError.
"""

from __future__ import annotations

import builtins
import inspect
import unittest
from pathlib import Path
from unittest.mock import patch

from epg_renderer import gui, render_io
from epg_renderer.render_options import RasterDependencyError


def _import_failing(module: str, error: Exception):
    original_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):
        if name == module:
            raise error
        return original_import(name, *args, **kwargs)

    return patch("builtins.__import__", side_effect=blocked_import)


class RasterAvailabilityTests(unittest.TestCase):
    def test_available_when_the_raster_modules_load(self) -> None:
        with patch.object(render_io, "_load_raster_dependencies", return_value=(None, None)):
            self.assertTrue(render_io.raster_output_available())

    def test_unavailable_when_a_raster_package_is_missing(self) -> None:
        for module in ("cairosvg", "PIL"):
            with self.subTest(module=module), _import_failing(module, ImportError(module)):
                self.assertFalse(render_io.raster_output_available())

    def test_unavailable_when_the_native_cairo_library_is_missing(self) -> None:
        missing_library = OSError("no library called 'cairo-2' was found")
        with _import_failing("cairosvg", missing_library):
            self.assertFalse(render_io.raster_output_available())

    def test_missing_packages_still_raise_the_actionable_error_when_rendering(self) -> None:
        with (
            _import_failing("cairosvg", ImportError("cairosvg")),
            self.assertRaises(RasterDependencyError),
        ):
            render_io._load_raster_dependencies()


class DefaultImageFormatTests(unittest.TestCase):
    def test_png_is_preselected_when_raster_output_works(self) -> None:
        with patch.object(gui, "raster_output_available", return_value=True):
            self.assertEqual(gui.default_image_format(), "png")

    def test_svg_is_preselected_without_raster_output(self) -> None:
        with patch.object(gui, "raster_output_available", return_value=False):
            self.assertEqual(gui.default_image_format(), "svg")

    def test_main_window_starts_with_the_default_format(self) -> None:
        # The window itself needs a display; its constructor is checked in the source.
        source = inspect.getsource(gui.EpgRendererApp.__init__)
        self.assertIn("self.format_var = tk.StringVar(value=default_image_format())", source)


class DefaultFormatDocumentationTests(unittest.TestCase):
    def test_gui_guide_states_which_format_is_preselected(self) -> None:
        guide = (Path(__file__).resolve().parents[1] / "docs" / "GETTING_STARTED.md").read_text(
            encoding="utf-8"
        )
        section = guide.split("## Choose the output format\n", 1)[1].split("\n## ", 1)[0]
        text = " ".join(section.split())
        self.assertIn("PNG is preselected when PNG and JPG output is available", text)
        self.assertIn("otherwise SVG", text)


if __name__ == "__main__":
    unittest.main()
