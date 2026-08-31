from __future__ import annotations

import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from epg_renderer import (
    render_batch,
    render_file,
)
from epg_renderer.render_options import OutputFormat

NS = {"svg": "http://www.w3.org/2000/svg"}
ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "globalfiler_minimal.tsv"


class BatchRenderingTests(unittest.TestCase):
    def _multi_sample_file(self, directory: Path) -> Path:
        text = FIXTURE.read_text(encoding="utf-8")
        second = "\n".join(
            line.replace("S1\t", "Sample / Two\t", 1) for line in text.splitlines()[1:]
        )
        path = directory / "multi.tsv"
        path.write_text(text.rstrip() + "\n" + second + "\n", encoding="utf-8")
        return path

    def test_batch_renders_every_sample_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = render_batch(
                self._multi_sample_file(root), root / "out", kit_name="GlobalFiler"
            )
            self.assertEqual(result.output_format, OutputFormat.SVG)
            self.assertEqual(result.succeeded, 2)
            self.assertEqual(result.failed, 0)
            self.assertTrue((root / "out" / "S1.svg").is_file())
            self.assertTrue((root / "out" / "Sample___Two.svg").is_file())
            payload = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["succeeded"], 2)
            self.assertEqual(payload["kit_name"], "GlobalFiler")

    def test_batch_rejects_unknown_format(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError):
            render_batch(FIXTURE, Path(tmp), output_format="bmp")


class BatchDesignTests(unittest.TestCase):
    def _root(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "example.svg"
            render_file(FIXTURE, path, kit_name="GlobalFiler")
            return ET.parse(path).getroot()

    def test_amelogenin_display_name_uses_fixed_short_label(self):
        root = self._root()
        labels = [node.text for node in root.findall('.//svg:text[@class="marker-label"]', NS)]
        self.assertIn("A...", labels)
        self.assertNotIn("AMEL", labels)
        self.assertNotIn("Amelogenin", labels)

    def test_three_rfu_axis_values_per_channel(self):
        root = self._root()
        for panel in root.findall('.//svg:g[@class="channel-panel"]', NS):
            ticks = panel.findall('.//svg:text[@class="rfu-label"]', NS)
            self.assertEqual(len(ticks), 3)

    def test_x_domain_starts_close_to_first_marker(self):
        root = self._root()
        metadata = json.loads(root.find("svg:metadata", NS).text)
        self.assertEqual(float(metadata["x_min_bp"]), 70.0)


if __name__ == "__main__":
    unittest.main()
