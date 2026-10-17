"""New in 0.16.1: the check tools end with one short block and a clear verdict.

``tools.run_all_tests``, ``tools.run_quality_checks``, ``tools.run_coverage_checks`` and
``tools.run_release_checks`` print the same framed block, modelled on STRio's runner;
``run_release_checks --skip-build`` gives one summary of everything CI checks.
"""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import tools.run_all_tests as run_all_tests
import tools.run_coverage_checks as run_coverage_checks
import tools.run_quality_checks as run_quality_checks
import tools.run_release_checks as run_release_checks
from tools.console_report import block, package_version, row
from tools.coverage_policy import COVERAGE_TARGETS

ROOT = Path(__file__).resolve().parents[1]


def _demo_case() -> type[unittest.TestCase]:
    """Build the demo case inside a function so that discovery does not collect it."""

    class _Demo(unittest.TestCase):
        def test_pass_quietly(self) -> None:
            print("noise of a passing test")

        def test_fail_in_two_subtests(self) -> None:
            for value in (1, 2):
                with self.subTest(value=value):
                    self.assertEqual(value, 0)

        def test_error(self) -> None:
            raise RuntimeError("boom")

        @unittest.skip("no raster here")
        def test_skip(self) -> None:
            pass

    return _Demo


def _payload(low_module: str | None = None) -> dict[str, object]:
    files = {}
    for target in COVERAGE_TARGETS:
        covered = 10 if target.module == low_module else 100
        files[f"src/epg_renderer/{target.module}"] = {
            "summary": {
                "num_statements": 100,
                "covered_lines": covered,
                "num_branches": 10,
                "covered_branches": 10,
            }
        }
    return {"files": files}


class ConsoleBlockTests(unittest.TestCase):
    def test_block_frames_rows_and_ends_with_the_verdict(self) -> None:
        text = block("Title", [row("Tests run", 12), row("Ruff lint", "passed")], True)
        lines = text.splitlines()
        self.assertEqual(lines[0], "=" * 50)
        self.assertEqual(lines[1], "Title")
        self.assertIn("Tests run                  12", lines)
        self.assertIn("Ruff lint              passed", lines)
        self.assertEqual(lines[-2:], ["Result: PASSED", "=" * 50])
        self.assertIn("Result: FAILED", block("Title", [], False))

    def test_version_is_read_from_the_package(self) -> None:
        from epg_renderer.version import __version__

        self.assertEqual(package_version(ROOT), __version__)


class TestRunnerReportTests(unittest.TestCase):
    def _main(self, *arguments: str) -> tuple[int, str, dict[str, object]]:
        tests = tuple(
            run_all_tests.iter_tests(unittest.defaultTestLoader.loadTestsFromTestCase(_demo_case()))
        )
        ids = tuple(test.id() for test in tests)
        with tempfile.TemporaryDirectory() as directory:
            summary_path = Path(directory) / "summary.json"
            with (
                mock.patch.object(
                    run_all_tests, "discover_tests", return_value=(unittest.TestSuite(tests), ids)
                ),
                mock.patch.dict(os.environ, {run_all_tests.SUMMARY_VARIABLE: str(summary_path)}),
                mock.patch("sys.stdout", new_callable=io.StringIO) as stdout,
            ):
                code = run_all_tests.main(list(arguments))
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        return code, stdout.getvalue(), summary

    def test_report_counts_by_test_and_holds_back_output_of_passing_tests(self) -> None:
        code, output, summary = self._main()
        self.assertEqual(code, 1)
        self.assertNotIn("noise of a passing test", output)
        self.assertRegex(output, r"Tests run\s+4\nPassed\s+1\nFailed\s+1\nErrors\s+1\nSkipped\s+1")
        self.assertEqual(
            {key: summary[key] for key in ("total", "passed", "failed", "errors", "skipped")},
            {"total": 4, "passed": 1, "failed": 1, "errors": 1, "skipped": 1},
        )

    def test_problems_follow_the_block_with_their_last_line(self) -> None:
        _, output, _ = self._main()
        verdict = output.index("Result: FAILED")
        self.assertGreater(output.index("ERROR: test_error"), verdict)
        self.assertIn("    RuntimeError: boom", output)
        self.assertIn("SKIPPED: test_skip", output)
        self.assertIn("    no raster here", output)

    def test_verbose_lists_every_test(self) -> None:
        _, output, _ = self._main("-v")
        self.assertIn("test_pass_quietly", output.split("=" * 50)[0])


class QualityReportTests(unittest.TestCase):
    def _main(self, failing: str | None) -> tuple[int, str]:
        def fake_run(command: list[str], **_: object) -> mock.Mock:
            failed = failing is not None and failing in command
            return mock.Mock(returncode=1 if failed else 0, stdout="tool says why", stderr="")

        with (
            mock.patch.object(run_quality_checks.importlib.util, "find_spec", return_value=1),
            mock.patch.object(run_quality_checks.subprocess, "run", side_effect=fake_run),
            mock.patch("sys.stdout", new_callable=io.StringIO) as stdout,
        ):
            code = run_quality_checks.main()
        return code, stdout.getvalue()

    def test_passing_checks_print_only_the_block(self) -> None:
        code, output = self._main(failing=None)
        self.assertEqual(code, 0)
        self.assertNotIn("tool says why", output)
        for label in ("Ruff lint", "Ruff format", "MyPy strict", "Compileall"):
            self.assertRegex(output, rf"{label}\s+passed")
        self.assertTrue(output.rstrip().endswith("Result: PASSED\n" + "=" * 50))

    def test_a_failing_check_shows_its_output_above_the_block(self) -> None:
        code, output = self._main(failing="mypy")
        self.assertEqual(code, 1)
        self.assertLess(output.index("tool says why"), output.index("=" * 50))
        self.assertRegex(output, r"MyPy strict\s+FAILED")
        self.assertIn("Result: FAILED", output)

    def test_missing_tools_are_listed_in_the_block(self) -> None:
        with (
            mock.patch.object(run_quality_checks.importlib.util, "find_spec", return_value=None),
            mock.patch("sys.stdout", new_callable=io.StringIO) as stdout,
            mock.patch("sys.stderr", new_callable=io.StringIO),
        ):
            self.assertEqual(run_quality_checks.main(), 2)
        self.assertRegex(stdout.getvalue(), r"mypy\s+NOT INSTALLED")
        self.assertIn("Result: FAILED", stdout.getvalue())


class CoverageReportTests(unittest.TestCase):
    def test_passing_coverage_shows_package_figures_and_targets(self) -> None:
        payload = _payload()
        report = run_coverage_checks.format_report("9.9.9", payload, [])
        self.assertRegex(report, r"Package lines\s+100\.00 %")
        self.assertIn(f"{len(COVERAGE_TARGETS)} of {len(COVERAGE_TARGETS)} met", report)
        self.assertIn("Result: PASSED", report)

    def test_a_missed_target_is_counted_exactly_and_listed(self) -> None:
        payload = _payload(low_module="gui_workflow.py")
        failures = run_coverage_checks.evaluate_coverage_payload(payload)
        report = run_coverage_checks.format_report("9.9.9", payload, failures)
        self.assertIn(f"{len(COVERAGE_TARGETS) - 1} of {len(COVERAGE_TARGETS)} met", report)
        self.assertIn("MISSED: gui_workflow.py: line coverage", report)
        self.assertGreater(report.index("MISSED:"), report.index("Result: FAILED"))
        self.assertFalse(run_coverage_checks._target_missed("workflow.py", failures))

    def test_failed_tests_leave_coverage_unevaluated(self) -> None:
        report = run_coverage_checks.format_report("9.9.9", None, [])
        self.assertIn("not evaluated", report)
        self.assertIn("Result: FAILED", report)

    @staticmethod
    def _measure_output(payload: dict[str, object], verbose: bool) -> str:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)

            def fake_run(_root: Path, *arguments: str, **_: object) -> mock.Mock:
                if "json" in arguments:
                    (workspace / "coverage.json").write_text(json.dumps(payload))
                return mock.Mock(returncode=0, stdout="THE TABLE", stderr="")

            with (
                mock.patch.object(run_coverage_checks, "_run", side_effect=fake_run),
                mock.patch("sys.stdout", new_callable=io.StringIO) as stdout,
            ):
                run_coverage_checks._measure(ROOT, workspace, verbose)
        return stdout.getvalue()

    def test_the_table_is_shown_only_when_a_threshold_is_missed_or_asked_for(self) -> None:
        for payload, verbose, shown in (
            (_payload(), False, False),
            (_payload(), True, True),
            (_payload(low_module="api.py"), False, True),
        ):
            with self.subTest(verbose=verbose, shown=shown):
                self.assertEqual("THE TABLE" in self._measure_output(payload, verbose), shown)


class ReleaseSummaryTests(unittest.TestCase):
    def _main(self, *arguments: str, failing: str | None = None) -> tuple[int, str, list[str]]:
        calls: list[str] = []

        def fake_run(_root: Path, label: str, *_args: str, environment: dict[str, str]) -> bool:
            calls.append(label)
            if label == "Tests and coverage":
                counts = {"total": 9, "passed": 8, "failed": 0, "errors": 0, "skipped": 1}
                path = Path(environment[run_release_checks.SUMMARY_VARIABLE])
                path.write_text(json.dumps(counts), encoding="utf-8")
            return label != failing

        with (
            mock.patch.object(run_release_checks, "_run", side_effect=fake_run),
            mock.patch.object(run_release_checks, "build_reproducible_release") as build,
            mock.patch("sys.stdout", new_callable=io.StringIO) as stdout,
        ):
            code = run_release_checks.main(list(arguments))
        if build.called:
            calls.append("Release build")
        return code, stdout.getvalue(), calls

    def test_skip_build_runs_quality_and_covered_tests_and_sums_up(self) -> None:
        code, output, calls = self._main("--skip-build")
        self.assertEqual(code, 0)
        self.assertEqual(calls, ["Static quality", "Tests and coverage"])
        final = output[output.rindex("release checks") :]
        self.assertRegex(final, r"Release build\s+skipped")
        self.assertRegex(final, r"Tests run\s+9\n  passed\s+8\n  failed\s+0")
        self.assertTrue(final.rstrip().endswith("Result: PASSED\n" + "=" * 50))

    def test_without_the_flag_the_release_is_built(self) -> None:
        code, output, calls = self._main()
        self.assertEqual(code, 0)
        self.assertIn("Release build", calls)
        self.assertRegex(output, r"Release build\s+passed")

    def test_a_failing_stage_stops_the_run_and_fails_the_summary(self) -> None:
        code, output, calls = self._main("--skip-build", failing="Static quality")
        self.assertEqual(code, 1)
        self.assertEqual(calls, ["Static quality"])
        self.assertRegex(output, r"Static quality\s+FAILED")
        self.assertRegex(output, r"Tests and coverage\s+not run")
        self.assertIn("Result: FAILED", output)

    def test_output_dir_needs_the_build(self) -> None:
        with (
            mock.patch("sys.stderr", new_callable=io.StringIO),
            self.assertRaises(SystemExit) as caught,
        ):
            run_release_checks.main(["--skip-build", "--output-dir", "out"])
        self.assertEqual(caught.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
