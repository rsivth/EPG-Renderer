"""Regressions for the single atomic file writer.

SVG text and raster bytes share one atomic write implementation. Text is stored as
UTF-8 without BOM and without newline translation; SVG write failures stay
``SvgRenderError`` and raster write failures stay ``RasterRenderError``; no temporary
file survives a success or a failure.
"""

from __future__ import annotations

import ast
import tempfile
import unittest
from pathlib import Path

from epg_renderer import render_io
from epg_renderer.render_options import RasterRenderError, SvgRenderError

SOURCE = Path(render_io.__file__)
TEXT = "line 1\nline 2\r\nµ – é ✓\n"


def _functions_creating_temporary_files() -> list[str]:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    names: list[str] = []
    for function in ast.walk(tree):
        if not isinstance(function, ast.FunctionDef):
            continue
        for node in ast.walk(function):
            if isinstance(node, ast.Attribute) and node.attr == "NamedTemporaryFile":
                names.append(function.name)
                break
    return names


class AtomicWriteTests(unittest.TestCase):
    def test_one_function_implements_the_atomic_write(self) -> None:
        self.assertEqual(len(_functions_creating_temporary_files()), 1)

    def test_text_is_written_as_exact_utf8_without_newline_translation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "out.svg"
            render_io._atomic_write_text(target, TEXT)
            self.assertEqual(target.read_bytes(), TEXT.encode("utf-8"))
            self.assertEqual(sorted(path.name for path in Path(directory).iterdir()), ["out.svg"])

    def test_text_write_replaces_existing_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "out.svg"
            target.write_bytes(b"old content that is longer than the new one")
            render_io._atomic_write_text(target, "new")
            self.assertEqual(target.read_bytes(), b"new")

    def test_failed_text_replace_raises_svg_error_and_leaves_no_temporary_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "out.svg"
            target.mkdir()
            with self.assertRaises(SvgRenderError) as raised:
                render_io._atomic_write_text(target, TEXT)
            self.assertNotIsInstance(raised.exception, RasterRenderError)
            self.assertIsInstance(raised.exception.__cause__, OSError)
            self.assertEqual(sorted(path.name for path in Path(directory).iterdir()), ["out.svg"])

    def test_failed_bytes_replace_raises_raster_error_and_leaves_no_temporary_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "out.png"
            target.mkdir()
            with self.assertRaises(RasterRenderError) as raised:
                render_io._atomic_write_bytes(target, b"data")
            self.assertIsInstance(raised.exception.__cause__, OSError)
            self.assertEqual(sorted(path.name for path in Path(directory).iterdir()), ["out.png"])


if __name__ == "__main__":
    unittest.main()
