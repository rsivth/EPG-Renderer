"""Regressions for diagnostics of single-file rendering through the package root.

``render_file`` returns only the output path. An image rendered with permissive
positioning can omit called peaks, so the package root must also offer an operation
that returns the parser warnings and positioning issues of the same rendering.
"""

from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

import epg_renderer
from epg_renderer import render_file_report
from epg_renderer.kit_registry import get_coordinate_model
from epg_renderer.render_options import SvgRenderOptions, UnpositionedPolicy
from epg_renderer.workflow import RenderReport

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "globalfiler_minimal.tsv"
KIT = "GlobalFiler"
MARKER = "D3S1358"


def _export_with_omitted_peak(directory: Path) -> Path:
    outside = get_coordinate_model(KIT).marker(MARKER).range_max_bp + Decimal("0.5")
    path = directory / "export.tsv"
    path.write_text(
        f"Sample Name\tMarker\tAllele 1\tSize 1\tHeight 1\t\nS1\t{MARKER}\t16\t{outside}\t800\t\n",
        encoding="utf-8",
    )
    return path


class RenderFileReportTests(unittest.TestCase):
    def test_package_root_exports_the_report_operation(self) -> None:
        self.assertIn("render_file_report", epg_renderer.__all__)

    def test_clean_render_returns_report_without_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "sample.svg"
            report = render_file_report(FIXTURE, target, kit_name=KIT)
            self.assertIsInstance(report, RenderReport)
            self.assertEqual(report.output_path, target)
            self.assertTrue(target.is_file())
        self.assertEqual(report.messages(), ())
        self.assertFalse(report.has_omitted_peaks)

    def test_report_exposes_omitted_peaks_and_parser_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = render_file_report(
                _export_with_omitted_peak(root),
                root / "sample.svg",
                kit_name=KIT,
                strict_positioning=False,
                options=SvgRenderOptions(unpositioned_policy=UnpositionedPolicy.OMIT),
            )
            self.assertTrue(report.output_path.is_file())
        self.assertTrue(report.has_omitted_peaks)
        self.assertTrue(any("unnamed trailing column" in text for text in report.warnings))
        self.assertTrue(any(MARKER in text for text in report.messages()))


if __name__ == "__main__":
    unittest.main()
