from __future__ import annotations

import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from epg_renderer import render_file

NS = {"svg": "http://www.w3.org/2000/svg"}
ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "globalfiler_minimal.tsv"


class LabelRenderingTests(unittest.TestCase):
    def _root(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "example.svg"
            render_file(FIXTURE, path, kit_name="GlobalFiler")
            return ET.parse(path).getroot()

    def test_baseline_segments_have_round_linecaps(self):
        root = self._root()
        colored = root.findall('.//svg:line[@class="axis-line channel-baseline-segment"]', NS)
        self.assertTrue(colored)
        self.assertEqual({line.attrib.get("stroke-linecap") for line in colored}, {"round"})

    def test_peak_contours_stop_cleanly_at_the_baseline(self):
        root = self._root()
        peaks = root.findall('.//svg:path[@class="allele-peak-shape"]', NS)
        self.assertTrue(peaks)
        self.assertEqual({node.attrib.get("stroke-linecap") for node in peaks}, {"butt"})


if __name__ == "__main__":
    unittest.main()
