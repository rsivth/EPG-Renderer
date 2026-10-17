"""Discover and run the complete current EPG-Renderer test suite with a short report.

Usage (from the repository root)::

    python -m tools.run_all_tests        # short report
    python -m tools.run_all_tests -v     # additionally list every test as it runs

Output that tests print is held back and shown only for tests that fail. The report
ends with ``Result: PASSED`` or ``Result: FAILED``; the exit code is 0 or 1 (2 if the
suite cannot be discovered). If the environment variable named by ``SUMMARY_VARIABLE``
holds a file path, the counts are also written there as JSON, so that
``tools.run_release_checks`` can show them in its own summary.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import platform
import sys
import time
import unittest
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path

from tools.console_report import block, row

SUMMARY_VARIABLE = "EPG_RENDERER_TEST_SUMMARY"


class TestDiscoveryError(RuntimeError):
    """Raised when test discovery produces duplicate identifiers."""


@dataclass
class TestSummary:
    """Counts of one run, by test (a test with failing sub-tests counts once)."""

    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    duration: float = 0.0
    successful: bool = True
    problems: list[tuple[str, str, str]] = field(default_factory=list)


def iter_tests(suite: unittest.TestSuite) -> Iterator[unittest.TestCase]:
    """Yield every test case from a possibly nested unittest suite."""

    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from iter_tests(item)
        else:
            yield item


def discover_tests(
    root: Path,
    loader: unittest.TestLoader | None = None,
) -> tuple[unittest.TestSuite, tuple[str, ...]]:
    """Discover every current ``test*.py`` module without exclusions."""

    selected_loader = loader or unittest.defaultTestLoader
    suite = selected_loader.discover(str(root / "tests"), pattern="test*.py")
    tests = tuple(iter_tests(suite))
    test_ids = tuple(test.id() for test in tests)
    if len(test_ids) != len(set(test_ids)):
        duplicates = sorted({test_id for test_id in test_ids if test_ids.count(test_id) > 1})
        raise TestDiscoveryError(f"Duplicate discovered test IDs: {duplicates}")
    return unittest.TestSuite(tests), test_ids


def _base_id(test: object) -> str:
    """Return the identifier of a test, or of the test that owns a sub-test."""

    owner = getattr(test, "test_case", test)
    return str(owner.id()) if hasattr(owner, "id") else str(owner)


def _last_line(text: str) -> str:
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    return lines[-1] if lines else ""


def summarize(
    test_ids: tuple[str, ...], result: unittest.TestResult, duration: float
) -> TestSummary:
    """Count a finished run by test and collect failures, errors and skips."""

    failed = {_base_id(test) for test, _ in result.failures}
    errored = {_base_id(test) for test, _ in result.errors} - failed
    skipped = {_base_id(test) for test, _ in result.skipped} - failed - errored
    unexpected = {_base_id(test) for test in result.unexpectedSuccesses}
    summary = TestSummary(
        total=len(test_ids),
        passed=len(test_ids) - len(failed | errored | skipped | unexpected),
        failed=len(failed | unexpected),
        errors=len(errored),
        skipped=len(skipped),
        duration=duration,
        successful=result.wasSuccessful(),
    )
    for label, entries in (("FAILED", result.failures), ("ERROR", result.errors)):
        summary.problems.extend((label, str(test), _last_line(trace)) for test, trace in entries)
    summary.problems.extend(
        ("UNEXPECTED SUCCESS", str(test), "") for test in result.unexpectedSuccesses
    )
    summary.problems.extend(("SKIPPED", str(test), reason) for test, reason in result.skipped)
    return summary


def format_report(summary: TestSummary, version: str) -> str:
    """Return the short report; problems follow the block that holds the verdict."""

    rows = [
        row("Tests run", summary.total),
        row("Passed", summary.passed),
        row("Failed", summary.failed),
        row("Errors", summary.errors),
        row("Skipped", summary.skipped),
        row("Duration", f"{summary.duration:>6.1f} s"),
    ]
    title = f"EPG-Renderer {version} · tests · Python {platform.python_version()}"
    lines = [block(title, rows, summary.successful)]
    for label, test, message in summary.problems:
        lines.append(f"{label}: {test}")
        if message:
            lines.append(f"    {message}")
    return "\n".join(lines)


def _write_summary(summary: TestSummary) -> None:
    target = os.environ.get(SUMMARY_VARIABLE)
    if target:
        Path(target).write_text(json.dumps(asdict(summary)), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """Discover and run every current test exactly once."""

    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("-v", "--verbose", action="store_true", help="list every test")
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))
    sys.path.insert(0, str(root / "tests"))

    try:
        suite, test_ids = discover_tests(root)
    except TestDiscoveryError as exc:
        print(f"Test discovery error: {exc}", file=sys.stderr)
        return 2
    from epg_renderer.version import __version__

    stream = sys.stdout if args.verbose else io.StringIO()
    runner = unittest.TextTestRunner(
        stream=stream, verbosity=2 if args.verbose else 0, buffer=not args.verbose
    )
    start = time.perf_counter()
    result = runner.run(suite)
    summary = summarize(test_ids, result, time.perf_counter() - start)
    _write_summary(summary)
    if args.verbose:
        print()
    print(format_report(summary, __version__), flush=True)
    return 0 if summary.successful else 1


if __name__ == "__main__":
    raise SystemExit(main())
