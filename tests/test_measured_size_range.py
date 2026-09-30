"""Regressions for exported sizes that lie outside the kit's marker range.

A GeneMapper ``Size n`` value is a measured fragment size. When it falls outside the
nominal marker range of the selected kit, positioning must fail with a diagnosable
positioning error in strict mode and record an omitted-peak issue in permissive mode,
instead of raising a bare ``ValueError`` that aborts a whole batch.
"""

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from epg_renderer import position_sample, render_batch
from epg_renderer.cli import main as cli_main
from epg_renderer.domain import BatchStatus
from epg_renderer.kit_registry import get_coordinate_model
from epg_renderer.models import AlleleCall, MarkerCall, SampleCall
from epg_renderer.positions import PeakCoordinateSource, PositionModelError
from epg_renderer.workflow import OMITTED_PEAK_ISSUE_CODES

KIT = "GlobalFiler"
MARKER = "D3S1358"
ISSUE_CODE = "measured_size_outside_range"


def _marker_range() -> tuple[Decimal, Decimal]:
    definition = get_coordinate_model(KIT).marker(MARKER)
    return definition.range_min_bp, definition.range_max_bp


def _sample(size_bp: Decimal) -> SampleCall:
    call = AlleleCall(allele_index=1, allele="16", height=800, size_bp=size_bp)
    return SampleCall("S1", {MARKER: MarkerCall(MARKER, None, (call,))})


def _export_text(outside_size: Decimal, inside_size: Decimal) -> str:
    return (
        "Sample Name\tMarker\tAllele 1\tSize 1\tHeight 1\n"
        f"BAD\t{MARKER}\t16\t{outside_size}\t800\n"
        f"GOOD\t{MARKER}\t16\t{inside_size}\t800\n"
    )


class MeasuredSizeOutsideRangeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.range_min, self.range_max = _marker_range()
        self.outside = self.range_max + Decimal("0.5")
        self.inside = (self.range_min + self.range_max) / 2

    def test_strict_positioning_raises_a_positioning_error_with_context(self) -> None:
        with self.assertRaises(PositionModelError) as context:
            position_sample(_sample(self.outside), kit_name=KIT)
        message = str(context.exception)
        self.assertIn(MARKER, message)
        self.assertIn(str(self.outside), message)

    def test_permissive_positioning_records_issue_and_leaves_peak_unpositioned(self) -> None:
        positioned = position_sample(_sample(self.outside), kit_name=KIT, strict=False)
        self.assertEqual([issue.code for issue in positioned.issues], [ISSUE_CODE])
        (peak,) = positioned.peaks
        self.assertIsNone(peak.coordinate_bp)
        self.assertIs(peak.coordinate_source, PeakCoordinateSource.UNPOSITIONED)

    def test_size_on_the_range_boundary_remains_a_measured_coordinate(self) -> None:
        positioned = position_sample(_sample(self.range_max), kit_name=KIT)
        (peak,) = positioned.peaks
        self.assertEqual(peak.coordinate_bp, self.range_max)
        self.assertIs(peak.coordinate_source, PeakCoordinateSource.MEASURED)
        self.assertEqual(positioned.issues, ())

    def test_issue_counts_as_an_omitted_peak(self) -> None:
        self.assertIn(ISSUE_CODE, OMITTED_PEAK_ISSUE_CODES)

    def test_strict_batch_isolates_the_failing_sample(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "export.tsv"
            source.write_text(_export_text(self.outside, self.inside), encoding="utf-8")
            result = render_batch(source, root / "out", kit_name=KIT)
        status = {item.sample_id: item.status for item in result.items}
        self.assertEqual(status, {"BAD": BatchStatus.FAILED, "GOOD": BatchStatus.SUCCEEDED})
        failed = next(item for item in result.items if item.sample_id == "BAD")
        self.assertIn(MARKER, failed.error or "")
        self.assertNotIn("Unexpected", failed.error or "")

    def test_permissive_cli_reports_incomplete_output_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "export.tsv"
            source.write_text(_export_text(self.outside, self.inside), encoding="utf-8")
            stderr = io.StringIO()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(stderr):
                status = cli_main(
                    [
                        str(source),
                        str(root / "bad.svg"),
                        "--sample-id",
                        "BAD",
                        "--kit",
                        KIT,
                        "--permissive-positioning",
                    ]
                )
        self.assertEqual(status, 3, stderr.getvalue())
        self.assertIn(MARKER, stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
