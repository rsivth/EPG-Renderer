"""Run the test suite once under coverage and enforce line and branch thresholds."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from tools.coverage_policy import (
    COVERAGE_TARGETS,
    MINIMUM_PACKAGE_BRANCH_COVERAGE,
    MINIMUM_PACKAGE_LINE_COVERAGE,
)


def _run(
    root: Path, *arguments: str, environment: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *arguments], cwd=root, check=False, text=True, env=environment
    )


def _percent(covered: int, total: int) -> float:
    return 100.0 if total == 0 else covered * 100.0 / total


def _line_percent(summary: dict[str, Any]) -> float:
    return _percent(int(summary["covered_lines"]), int(summary["num_statements"]))


def _branch_percent(summary: dict[str, Any]) -> float:
    return _percent(int(summary.get("covered_branches", 0)), int(summary.get("num_branches", 0)))


def evaluate_coverage_payload(payload: dict[str, Any]) -> list[str]:
    """Return threshold failures from a coverage JSON payload."""

    failures: list[str] = []
    files = payload.get("files", {})
    package = [
        value["summary"] for path, value in files.items() if "epg_renderer" in Path(path).parts
    ]
    line_total = sum(int(item["num_statements"]) for item in package)
    line_covered = sum(int(item["covered_lines"]) for item in package)
    branch_total = sum(int(item.get("num_branches", 0)) for item in package)
    branch_covered = sum(int(item.get("covered_branches", 0)) for item in package)
    package_line = _percent(line_covered, line_total)
    package_branch = _percent(branch_covered, branch_total)
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


def main() -> int:
    """Execute tests under coverage and return a release-gate status."""

    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="epg-renderer-coverage-") as directory:
        workspace = Path(directory)
        environment = {
            **os.environ,
            "COVERAGE_FILE": str(workspace / ".coverage"),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        test_result = _run(
            root,
            "-m",
            "coverage",
            "run",
            "-m",
            "tools.run_all_tests",
            environment=environment,
        )
        if test_result.returncode != 0:
            return test_result.returncode
        json_path = workspace / "coverage.json"
        result = _run(
            root,
            "-m",
            "coverage",
            "json",
            "-o",
            str(json_path),
            environment=environment,
        )
        if result.returncode != 0:
            return result.returncode
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        report = _run(root, "-m", "coverage", "report", "-m", environment=environment)
        if report.returncode != 0:
            return report.returncode

    failures = evaluate_coverage_payload(payload)
    print()
    if failures:
        print("Coverage thresholds passed: no")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("Coverage thresholds passed: yes")
    for target in COVERAGE_TARGETS:
        print(
            f"- {target.module}: line >= {target.minimum_line_percent:.1f}%, "
            f"branch >= {target.minimum_branch_percent:.1f}%"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
