from __future__ import annotations

import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from epg_renderer import render_file
from epg_renderer.kit_workflow import KitResolutionError

FIXTURES = Path(__file__).with_name("fixtures")


class MultiKitWorkflowTests(unittest.TestCase):
    def test_globalfiler_auto_detection_still_works(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "gf.svg"
            render_file(FIXTURES / "globalfiler_minimal.tsv", target)
            root = ET.fromstring(target.read_text(encoding="utf-8"))
            self.assertEqual(root.attrib["data-kit"], "GlobalFiler")

    def test_ngm_auto_detection_and_rendering_work_end_to_end(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "ngm.svg"
            render_file(FIXTURES / "ngm_minimal.tsv", target)
            root = ET.fromstring(target.read_text(encoding="utf-8"))
            self.assertEqual(root.attrib["data-kit"], "NGM")
            self.assertEqual(root.attrib["data-coordinate-model-version"], "0.4-ngm1")

    def test_ngm_explicit_full_name_works(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "ngm.svg"
            render_file(
                FIXTURES / "ngm_minimal.tsv", target, kit_name="AmpFlSTR NGM PCR Amplification Kit"
            )
            self.assertTrue(target.is_file())

    def test_incompatible_explicit_kit_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(KitResolutionError):
            render_file(
                FIXTURES / "ngm_minimal.tsv", Path(directory) / "bad.svg", kit_name="GlobalFiler"
            )

    def test_svg_metadata_identifies_json_model(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "ngm.svg"
            render_file(FIXTURES / "ngm_minimal.tsv", target)
            root = ET.fromstring(target.read_text(encoding="utf-8"))
            metadata = next(element for element in root if element.tag.endswith("metadata"))
            payload = json.loads(metadata.text)
            self.assertEqual(payload["kit"], "NGM")
            self.assertEqual(payload["coordinate_model_version"], "0.4-ngm1")
            self.assertFalse(payload["exact_bin_centres"])

    def test_ngm_output_is_utf8_lf_and_atomic(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "ngm.svg"
            target.write_text("old", encoding="utf-8")
            render_file(FIXTURES / "ngm_minimal.tsv", target)
            data = target.read_bytes()
            self.assertTrue(data.startswith(b'<?xml version="1.0" encoding="UTF-8"?>'))
            self.assertNotIn(b"\r\n", data)
            self.assertEqual(list(Path(directory).glob(".*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
