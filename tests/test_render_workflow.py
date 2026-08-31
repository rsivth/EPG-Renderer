from __future__ import annotations

import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from epg_renderer import render_file
from epg_renderer.render_io import write_svg
from epg_renderer.render_options import (
    SampleSelectionError,
    SvgRenderError,
)

FIXTURES = Path(__file__).with_name("fixtures")


class RenderingWorkflowTests(unittest.TestCase):
    def test_convenience_function_writes_valid_svg(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "output.svg"
            returned = render_file(FIXTURES / "globalfiler_minimal.tsv", target)
            self.assertEqual(returned, target)
            self.assertTrue(target.is_file())
            root = ET.fromstring(target.read_text(encoding="utf-8"))
            self.assertEqual(root.attrib["data-kit"], "GlobalFiler")

    def test_convenience_function_creates_parent_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "nested" / "deeper" / "output.svg"
            render_file(FIXTURES / "globalfiler_minimal.tsv", target)
            self.assertTrue(target.is_file())

    def test_convenience_function_supports_explicit_kit_alias(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "output.svg"
            render_file(FIXTURES / "globalfiler_minimal.tsv", target, kit_name="GFI")
            root = ET.fromstring(target.read_text(encoding="utf-8"))
            self.assertEqual(root.attrib["data-kit"], "GlobalFiler")

    def test_multi_sample_export_requires_selection(self):
        source = (FIXTURES / "globalfiler_minimal.tsv").read_text(encoding="utf-8")
        header, *rows = source.splitlines()
        second = [row.replace("S1\t", "S2\t", 1) for row in rows]
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "multi.tsv"
            input_path.write_text("\n".join([header, *rows, *second]) + "\n", encoding="utf-8")
            with self.assertRaises(SampleSelectionError):
                render_file(input_path, Path(directory) / "output.svg")

    def test_selected_sample_is_rendered_from_multi_sample_export(self):
        source = (FIXTURES / "globalfiler_minimal.tsv").read_text(encoding="utf-8")
        header, *rows = source.splitlines()
        second = [row.replace("S1\t", "S2\t", 1) for row in rows]
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "multi.tsv"
            target = Path(directory) / "output.svg"
            input_path.write_text("\n".join([header, *rows, *second]) + "\n", encoding="utf-8")
            render_file(input_path, target, sample_id="S2")
            root = ET.fromstring(target.read_text(encoding="utf-8"))
            metadata = next(element for element in root if element.tag.endswith("metadata"))
            self.assertIn('"sample_id":"S2"', metadata.text)

    def test_unknown_sample_is_rejected_with_available_ids(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            self.assertRaisesRegex(SampleSelectionError, "Available samples"),
        ):
            render_file(
                FIXTURES / "globalfiler_minimal.tsv",
                Path(directory) / "output.svg",
                sample_id="missing",
            )

    def test_custom_sample_id_column_is_forwarded_to_parser(self):
        source = (FIXTURES / "globalfiler_minimal.tsv").read_text(encoding="utf-8")
        source = source.replace("Sample Name", "DNA ID", 1)
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "custom.tsv"
            target = Path(directory) / "output.svg"
            input_path.write_text(source, encoding="utf-8")
            render_file(input_path, target, sample_id_column="DNA ID")
            self.assertTrue(target.is_file())

    def test_write_svg_rejects_malformed_xml(self):
        with tempfile.TemporaryDirectory() as directory:
            malformed = '<?xml version="1.0" encoding="UTF-8"?><svg>'
            with self.assertRaises(SvgRenderError):
                write_svg(malformed, Path(directory) / "output.svg")

    def test_write_svg_rejects_non_renderer_text(self):
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(SvgRenderError):
            write_svg("<svg/>", Path(directory) / "output.svg")

    def test_atomic_write_replaces_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "output.svg"
            target.write_text("old", encoding="utf-8")
            render_file(FIXTURES / "globalfiler_minimal.tsv", target)
            self.assertNotEqual(target.read_text(encoding="utf-8"), "old")
            self.assertEqual(list(Path(directory).glob(".*.tmp")), [])

    def test_rendered_svg_uses_lf_line_endings(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "output.svg"
            render_file(FIXTURES / "globalfiler_minimal.tsv", target)
            data = target.read_bytes()
            self.assertNotIn(b"\r\n", data)
            self.assertTrue(data.endswith(b"\n"))


if __name__ == "__main__":
    unittest.main()
