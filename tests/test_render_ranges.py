from __future__ import annotations

import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from epg_renderer import render_file
from epg_renderer.render_metrics import _MARKER_LABEL_METRICS
from epg_renderer.render_svg import _fit_marker_label_text

NS = {"svg": "http://www.w3.org/2000/svg"}
ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "globalfiler_minimal.tsv"
NGM_DETECT_FIXTURE = ROOT / "tests" / "fixtures" / "ngm_detect_five_person_mixture.tsv"


class MarkerRangeRenderingTests(unittest.TestCase):
    def _root(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "example.svg"
            render_file(FIXTURE, path, kit_name="GlobalFiler")
            return ET.parse(path).getroot()

    def test_peak_paths_are_open_so_the_baseline_can_remain_black(self):
        root = self._root()
        paths = root.findall('.//svg:path[@class="allele-peak-shape"]', NS)
        self.assertTrue(paths)
        self.assertTrue(all(path.attrib.get("fill") == "#FFFFFF" for path in paths))
        self.assertTrue(all(not path.attrib["d"].strip().endswith("Z") for path in paths))

    def test_amel_marker_label_is_not_glyph_scaled(self):
        root = self._root()
        for node in root.findall('.//svg:text[@class="marker-label"]', NS):
            if node.text == "A...":
                self.assertNotIn("textLength", node.attrib)
                self.assertNotIn("lengthAdjust", node.attrib)
                break
        else:
            self.fail("A... marker label not found")

    def test_marker_band_and_default_label_size_use_shared_metrics(self):
        root = self._root()
        bands = root.findall('.//svg:g[@class="marker-band"]', NS)
        self.assertTrue(bands)
        used_default_size = False
        for band in bands:
            rect = band.find("svg:rect", NS)
            label = band.find("svg:text", NS)
            self.assertIsNotNone(rect)
            self.assertIsNotNone(label)
            self.assertEqual(float(rect.attrib["height"]), _MARKER_LABEL_METRICS.band_height_px)
            self.assertEqual(
                float(label.attrib["y"]) - float(rect.attrib["y"]),
                _MARKER_LABEL_METRICS.baseline_offset_px,
            )
            if "font-size" not in label.attrib:
                used_default_size = True
        self.assertTrue(used_default_size)

    def test_marker_label_fitting_truncates_when_the_band_is_too_short(self):
        label, font_size = _fit_marker_label_text("AMEL", band_width=18.0)
        self.assertEqual(label, "A…")
        self.assertEqual(font_size, _MARKER_LABEL_METRICS.fallback_font_size_px)

    def test_ngm_detect_uses_fixed_short_labels_at_the_existing_fallback_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ngm-detect.svg"
            render_file(NGM_DETECT_FIXTURE, path, kit_name="NGM Detect")
            root = ET.parse(path).getroot()

        expected = {"Yindel": "Y...", "Amelogenin": "A..."}
        found: dict[str, tuple[str, float]] = {}
        for band in root.findall('.//svg:g[@class="marker-band"]', NS):
            marker = band.attrib["data-marker"]
            if marker not in expected:
                continue
            label = band.find("svg:text", NS)
            self.assertIsNotNone(label)
            assert label is not None
            found[marker] = (label.text or "", float(label.attrib["font-size"]))

        self.assertEqual(
            found,
            {
                marker: (text, _MARKER_LABEL_METRICS.fallback_font_size_px)
                for marker, text in expected.items()
            },
        )


if __name__ == "__main__":
    unittest.main()
