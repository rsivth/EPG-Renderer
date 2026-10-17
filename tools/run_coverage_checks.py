"""Run the test suite once under coverage and enforce line and branch thresholds.

Usage (from the repository root)::

    python -m tools.run_coverage_checks      # short report
    python -m tools.run_coverage_checks -v   # additionally the full coverage table

The test run prints its own short report; the coverage table is shown only when a
threshold is missed (or with ``-v``). The output ends with the coverage block and its
``Result: PASSED`` or ``Result: FAILED``.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from tools.console_report import block, package_version, row
from tools.coverage_policy import (
    COVERAGE_TARGETS,
    MINIMUM_PACKAGE_BRANCH_COVERAGE,
    MINIMUM_PACKAGE_LINE_COVERAGE,
)


def _run(
    root: Path, *arguments: str, environment: dict[str, str], capture: bool = False
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *arguments],
        cwd=root,
        check=False,
        text=True,
        env=environment,
        capture_output=capture,
    )


def _percent(covered: int, total: int) -> float:
    return 100.0 if total == 0 else covered * 100.0 / total


def _line_percent(summary: dict[str, Any]) -> float:
    return _percent(int(summary["covered_lines"]), int(summary["num_statements"]))


def _branch_percent(summary: dict[str, Any]) -> float:
    return _percent(int(summary.get("covered_branches", 0)), int(summary.get("num_branches", 0)))


def package_coverage(payload: dict[str, Any]) -> tuple[float, float]:
    """Return the line and branch coverage of the whole package in percent."""

    files = payload.get("files", {})
    package = [
        value["summary"] for path, value in files.items() if "epg_renderer" in Path(path).parts
    ]
    line_total = sum(int(item["num_statements"]) for item in package)
    line_covered = sum(int(item["covered_lines"]) for item in package)
    branch_total = sum(int(item.get("num_branches", 0)) for item in package)
    branch_covered = sum(int(item.get("covered_branches", 0)) for item in package)
    return _percent(line_covered, line_total), _percent(branch_covered, branch_total)


def evaluate_coverage_payload(payload: dict[str, Any]) -> list[str]:
    """Return threshold failures from a coverage JSON payload."""

    failures: list[str] = []
    files = payload.get("files", {})
    package_line, package_branch = package_coverage(payload)
    if package_line + 1e-9 < MINIMUM_PACKAGE_LINE_COVERAGE:
        failures.append(
            f"Package line coverage {package_line:.2f}% is below "
            f"{MINIMUM_PACKAGE_LINE_COVERAGE:.2f}%."
        )
    if package_branch + 1e-9 < MINIMUM_PACKAGE_BRANCH_COVERAGE:
        failures.append(
            f"Package branch coverage {package_branch:.2f}% is below "
            f"{MINIMUM_PACKAGE_BRANCH_COVERAGE:.2f}%."
        )

    by_name = {Path(path).name: value["summary"] for path, value in files.items()}
    for target in COVERAGE_TARGETS:
        summary = by_name.get(target.module)
        if summary is None:
            failures.append(f"Coverage data are missing for {target.module}.")
            continue
        line = _line_percent(summary)
        branch = _branch_percent(summary)
        if line + 1e-9 < target.minimum_line_percent:
            failures.append(
                f"{target.module}: line coverage {line:.2f}% is below "
                f"{target.minimum_line_percent:.2f}% ({target.rationale})"
            )
        if branch + 1e-9 < target.minimum_branch_percent:
            failures.append(
                f"{target.module}: branch coverage {branch:.2f}% is below "
                f"{target.minimum_branch_percent:.2f}% ({target.rationale})"
            )
    return failures


def _target_missed(module: str, failures: list[str]) -> bool:
    return any(
        failure.startswith(f"{module}:") or failure.endswith(f" for {module}.")
        for failure in failures
    )


def format_report(version: str, payload: dict[str, Any] | None, failures: list[str]) -> str:
    """Return the coverage block; ``payload`` is ``None`` when tests or coverage failed."""

    if payload is None:
        rows = [row("Coverage", "not evaluated (see above)")]
    else:
        line, branch = package_coverage(payload)
        met = sum(1 for target in COVERAGE_TARGETS if not _target_missed(target.module, failures))
        rows = [
            row("Package lines", f"{line:6.2f} %  (minimum {MINIMUM_PACKAGE_LINE_COVERAGE:.1f} %)"),
            row(
                "Package branches",
                f"{branch:6.2f} %  (minimum {MINIMUM_PACKAGE_BRANCH_COVERAGE:.1f} %)",
            ),
            row("Module targets", f"{met} of {len(COVERAGE_TARGETS)} met"),
        ]
    passed = payload is not None and not failures
    lines = [block(f"EPG-Renderer {version} · coverage", rows, passed)]
    lines.extend(f"MISSED: {failure}" for failure in failures)
    return "\n".join(lines)


def _measure(root: Path, workspace: Path, verbose: bool) -> dict[str, Any] | None:
    """Run the tests under coverage; return the JSON payload, or ``None`` on failure."""

    environment = {
        **os.environ,
        "COVERAGE_FILE": str(workspace / ".coverage"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    test_result = _run(
        root, "-m", "coverage", "run", "-m", "tools.run_all_tests", environment=environment
    )
    if test_result.returncode != 0:
        return None
    json_path = workspace / "coverage.json"
    result = _run(
        root,
        "-m",
        "coverage",
        "json",
        "-o",
        str(json_path),
        environment=environment,
        capture=True,
    )
    if result.returncode != 0:
        print(result.stdout + result.stderr, file=sys.stderr)
        return None
    payload: dict[str, Any] = json.loads(json_path.read_text(encoding="utf-8"))
    table = _run(root, "-m", "coverage", "report", "-m", environment=environment, capture=True)
    if verbose or evaluate_coverage_payload(payload):
        print(table.stdout + table.stderr, flush=True)
    return payload


def main(argv: list[str] | None = None) -> int:
    """Execute tests under coverage and return a release-gate status."""

    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("-v", "--verbose", action="store_true", help="show the full table")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="epg-renderer-coverage-") as directory:
        payload = _measure(root, Path(directory), args.verbose)
    failures = [] if payload is None else evaluate_coverage_payload(payload)
    print(format_report(package_version(root), payload, failures))
    return 0 if payload is not None and not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
