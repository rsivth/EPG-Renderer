"""Regressions for the GUI screenshot in the GUI guide.

Until 0.14.0.dev14 the GUI guide described the main window in words only. Since
0.14.0.dev15 it shows a screenshot of the window after opening the synthetic
GlobalFiler fixture. A screenshot can carry data from the machine it was taken on
(file paths, EXIF and XMP comments, the display's colour profile naming the monitor),
so the committed file must contain pixels only and stay small.
"""

from __future__ import annotations

import re
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs" / "GETTING_STARTED.md"
SCREENSHOT = ROOT / "docs" / "images" / "gui_main_window.png"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PIXEL_CHUNKS = {"IHDR", "PLTE", "IDAT", "IEND"}


def _chunk_types(data: bytes) -> list[str]:
    types: list[str] = []
    offset = len(PNG_SIGNATURE)
    while offset < len(data):
        (length,) = struct.unpack(">I", data[offset : offset + 4])
        types.append(data[offset + 4 : offset + 8].decode("ascii"))
        offset += 12 + length
    return types


class GuiScreenshotTests(unittest.TestCase):
    def test_screenshot_is_a_small_png_without_metadata(self) -> None:
        data = SCREENSHOT.read_bytes()
        self.assertTrue(data.startswith(PNG_SIGNATURE))
        self.assertLessEqual(len(data), 150_000)
        chunks = _chunk_types(data)
        self.assertEqual(chunks[0], "IHDR")
        self.assertEqual(chunks[-1], "IEND")
        self.assertEqual(set(chunks) - PIXEL_CHUNKS, set())

    def test_gui_guide_shows_the_screenshot_with_alternative_text(self) -> None:
        guide = GUIDE.read_text(encoding="utf-8")
        section = guide.split("## Create an image from a GeneMapper export\n", 1)[1]
        section = section.split("\n## ", 1)[0]
        match = re.search(r"!\[([^\]]+)\]\(images/gui_main_window\.png\)", section)
        self.assertIsNotNone(match)
        assert match is not None
        self.assertIn("main window", match[1])


if __name__ == "__main__":
    unittest.main()
