"""Contracts for surfacing parser warnings and positioning issues to users."""

from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from epg_renderer import load_project
from epg_renderer.cli import main
from epg_renderer.domain import PeakHeightMode
from epg_renderer.manual_profile import build_manual_profile, parse_manual_marker_text
from epg_renderer.render_options import SvgRenderOptions, UnpositionedPolicy
from epg_renderer.workflow import (
    DIAGNOSTICS_HEADING,
    OMITTED_PEAK_ISSUE_CODES,
    format_diagnostics,
    render_genemapper_epg_report,
    render_manual_epg_report,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "globalfiler_minimal.tsv"


def _fixture_with(*, trailing_column: bool = False, unknown_allele: bool = False) -> Path:
    lines = FIXTURE.read_text(encoding="utf-8").splitlines()
    header, body = lines[0], lines[1:]
    if unknown_allele:
        rebuilt = []
        for row in body:
            fields = row.split("\t")
            if fields[1] == "D3S1358":
                fields[3] = "77"
            rebuilt.append("\t".join(fields))
        body = rebuilt
    if trailing_column:
        header = header + "\t"
        body = [row + "\t" for row in body]
    target = Path(tempfile.mkdtemp()) / "input.tsv"
    target.write_text("\n".join([header, *body]) + "\n", encoding="utf-8")
    return target


class RenderReportTests(unittest.TestCase):
    """Keep parser warnings and positioning issues available to applications."""

    def test_report_exposes_parser_warnings(self) -> None:
        source = _fixture_with(trailing_column=True)
        output = Path(tempfile.mkdtemp()) / "out.svg"
        report = render_genemapper_epg_report(source, output, kit_name="GlobalFiler")
        self.assertEqual(report.output_path, output)
        self.assertTrue(any("trailing column" in warning for warning in report.warnings))
        self.assertEqual(report.issues, ())
        self.assertFalse(report.has_omitted_peaks)

    def test_report_exposes_unpositioned_peaks(self) -> None:
        source = _fixture_with(unknown_allele=True)
        output = Path(tempfile.mkdtemp()) / "out.svg"
        report = render_genemapper_epg_report(
            source,
            output,
            kit_name="GlobalFiler",
            strict_positioning=False,
            options=SvgRenderOptions(unpositioned_policy=UnpositionedPolicy.OMIT),
        )
        self.assertEqual([issue.code for issue in report.issues], ["unknown_allele"])
        self.assertTrue(report.has_omitted_peaks)
        self.assertTrue(any("77" in message for message in report.messages()))

    def test_report_is_clean_for_a_clean_export(self) -> None:
        output = Path(tempfile.mkdtemp()) / "out.svg"
        report = render_genemapper_epg_report(FIXTURE, output, kit_name="GlobalFiler")
        self.assertEqual(report.warnings, ())
        self.assertEqual(report.issues, ())
        self.assertFalse(report.has_omitted_peaks)
        self.assertEqual(report.messages(), ())


class DiagnosticsPresentationTests(unittest.TestCase):
    """Cover the shared text block the graphical interface displays in red."""

    def test_no_messages_produce_no_block(self) -> None:
        self.assertEqual(format_diagnostics(()), "")

    def test_every_message_is_listed_below_a_call_to_review(self) -> None:
        block = format_diagnostics(("first problem", "second problem"))
        lines = block.splitlines()
        self.assertEqual(lines[0], DIAGNOSTICS_HEADING)
        self.assertEqual(lines[1:], ["\u2022 first problem", "\u2022 second problem"])


class ManualProfileDiagnosticsTests(unittest.TestCase):
    """Manually entered profiles must report their diagnostics as well."""

    def _profile(self, allele: str):
        entry = parse_manual_marker_text("D3S1358", allele, "", PeakHeightMode.UNIFORM)
        assert entry is not None
        return build_manual_profile(
            "Manual",
            "GlobalFiler",
            {"D3S1358": entry},
            height_mode=PeakHeightMode.UNIFORM,
        )

    def test_manual_report_is_clean_for_a_ladder_allele(self) -> None:
        output = Path(tempfile.mkdtemp()) / "manual.svg"
        report = render_manual_epg_report(self._profile("15"), output)
        self.assertEqual(report.issues, ())
        self.assertFalse(report.has_omitted_peaks)
        self.assertEqual(report.output_path, output)


class OmittedPeakClassificationTests(unittest.TestCase):
    """Every issue code that removes a peak must raise the incomplete-output flag."""

    def test_off_ladder_without_size_counts_as_an_omitted_peak(self) -> None:
        self.assertIn("off_ladder_without_size", OMITTED_PEAK_ISSUE_CODES)
        self.assertIn("unknown_allele", OMITTED_PEAK_ISSUE_CODES)
        self.assertIn("missing_height", OMITTED_PEAK_ISSUE_CODES)

    def test_an_estimated_coordinate_is_reported_but_keeps_its_peak(self) -> None:
        source = FIXTURE.read_text(encoding="utf-8").splitlines()
        header, body = source[0], source[1:]
        rebuilt = []
        for row in body:
            fields = row.split("\t")
            if fields[1] == "D3S1358":
                fields[3] = "8"
            rebuilt.append("\t".join(fields))
        target = Path(tempfile.mkdtemp()) / "estimated.tsv"
        target.write_text("\n".join([header, *rebuilt]) + "\n", encoding="utf-8")
        output = Path(tempfile.mkdtemp()) / "out.svg"
        report = render_genemapper_epg_report(target, output, kit_name="GlobalFiler")
        self.assertEqual([issue.code for issue in report.issues], ["estimated_allele_coordinate"])
        self.assertFalse(report.has_omitted_peaks)
        self.assertTrue(report.messages())


class CommandLineDiagnosticsTests(unittest.TestCase):
    """Never let the command line report success while hiding lost peaks."""

    def _run(self, argv: list[str]) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            status = main(argv)
        return status, out.getvalue(), err.getvalue()

    def test_parser_warnings_reach_stderr_without_changing_the_exit_status(self) -> None:
        source = _fixture_with(trailing_column=True)
        output = Path(tempfile.mkdtemp()) / "out.svg"
        status, stdout, stderr = self._run(
            [str(source), str(output), "--kit", "GlobalFiler"],
        )
        self.assertEqual(status, 0)
        self.assertIn(str(output.resolve()), stdout)
        self.assertIn("trailing column", stderr)

    def test_omitted_peaks_are_reported_and_change_the_exit_status(self) -> None:
        source = _fixture_with(unknown_allele=True)
        output = Path(tempfile.mkdtemp()) / "out.svg"
        status, _stdout, stderr = self._run(
            [
                str(source),
                str(output),
                "--kit",
                "GlobalFiler",
                "--permissive-positioning",
            ],
        )
        self.assertEqual(status, 3)
        self.assertIn("77", stderr)
        self.assertIn("D3S1358", stderr)
        self.assertTrue(output.is_file())

    def test_a_clean_render_stays_silent_on_stderr(self) -> None:
        output = Path(tempfile.mkdtemp()) / "out.svg"
        status, _stdout, stderr = self._run(
            [str(FIXTURE), str(output), "--kit", "GlobalFiler"],
        )
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")

    def test_batch_manifest_records_warnings_and_issues(self) -> None:
        import json

        source = _fixture_with(trailing_column=True, unknown_allele=True)
        outdir = Path(tempfile.mkdtemp()) / "out"
        status, _stdout, _stderr = self._run(
            [
                str(source),
                str(outdir),
                "--all-samples",
                "--kit",
                "GlobalFiler",
                "--permissive-positioning",
            ],
        )
        manifest = json.loads((outdir / "epg_batch_manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(any("trailing column" in text for text in manifest["warnings"]))
        item = manifest["items"][0]
        self.assertEqual(item["status"], "ok")
        self.assertTrue(any("77" in text for text in item["issues"]))
        self.assertEqual(status, 3)


class ProjectWarningContractTests(unittest.TestCase):
    """Guard the parser-side contract the applications depend on."""

    def test_truncation_warning_is_produced_for_a_full_allele_row(self) -> None:
        project = load_project(
            ROOT / "tests" / "fixtures" / "genemapper_exports" / "essplex_se_qs_mixed_export.txt"
        )
        self.assertTrue(any("Allele 20" in warning for warning in project.warnings))


if __name__ == "__main__":
    unittest.main()
