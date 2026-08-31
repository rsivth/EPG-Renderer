from __future__ import annotations

import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from epg_renderer import render_file

NS = {"svg": "http://www.w3.org/2000/svg"}
ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "globalfiler_minimal.tsv"


class BaselineGapTests(unittest.TestCase):
    def _root(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "example.svg"
            render_file(FIXTURE, path, kit_name="GlobalFiler")
            return ET.parse(path).getroot()

    def test_no_black_or_colored_baseline_is_drawn_under_peak_footprints(self):
        root = self._root()
        self.assertEqual(
            root.findall('.//svg:line[@class="axis-line peak-baseline-segment"]', NS), []
        )
        colored = root.findall('.//svg:line[@class="axis-line channel-baseline-segment"]', NS)
        self.assertTrue(colored)


if __name__ == "__main__":
    unittest.main()
