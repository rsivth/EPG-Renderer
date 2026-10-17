"""Run the complete release gate without repeating the full test suite.

Usage (from the repository root)::

    python -m tools.run_release_checks               # before tagging a release
    python -m tools.run_release_checks --skip-build  # before every push: what CI checks

Stages: static quality checks, the reproducible release build (left out with
``--skip-build``), and one test run under coverage. A failing stage stops the run.
Every stage prints its own short report; the output always ends with a summary of all
stages, including the test counts, and its ``Result: PASSED`` or ``Result: FAILED``.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from tools.console_report import RULE, block, package_version, row
from tools.release_tools import ReleaseError, build_reproducible_release

SUMMARY_VARIABLE = "EPG_RENDERER_TEST_SUMMARY"
PASSED = "passed"
FAILED = "FAILED"
NOT_RUN = "not run"


def _run(root: Path, label: str, *arguments: str, environment: dict[str, str]) -> bool:
    print(f"\n== {label} ==", flush=True)
    result = subprocess.run([sys.executable, *arguments], cwd=root, check=False, env=environment)
    return result.returncode == 0


def _build(root: Path, output_dir: Path | None) -> bool:
    print("\n== Reproducible release ==", flush=True)
    try:
        if output_dir is None:
            with tempfile.TemporaryDirectory(prefix="epg-renderer-release-check-") as directory:
                build_reproducible_release(root, Path(directory))
        else:
            build_reproducible_release(root, output_dir.resolve())
    except ReleaseError as exc:
        print(f"Reproducible release: failed\n{exc}")
        return False
    print("Reproducible release: passed")
    return True


def _read_test_summary(path: Path) -> dict[str, object] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def format_summary(
    version: str, stages: list[tuple[str, str]], tests: dict[str, object] | None
) -> str:
    """Return the final block over all stages."""

    rows = [row(label, status) for label, status in stages]
    rows.append(RULE)
    if tests is None:
        rows.append(row("Tests", NOT_RUN if stages[-1][1] == NOT_RUN else "no counts"))
    else:
        for label, key in (
            ("Tests run", "total"),
            ("  passed", "passed"),
            ("  failed", "failed"),
            ("  errors", "errors"),
            ("  skipped", "skipped"),
        ):
            value = tests.get(key)
            rows.append(row(label, value if isinstance(value, int) else "?"))
    passed = all(status in (PASSED, "skipped") for _, status in stages)
    return block(f"EPG-Renderer {version} · release checks", rows, passed)


def main(argv: list[str] | None = None) -> int:
    """Run static checks, the reproducible build, and one covered test run."""

    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="retain the fully verified release artifacts in this directory",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="leave out the reproducible release build (the checks CI runs on every push)",
    )
    args = parser.parse_args(argv)
    if args.skip_build and args.output_dir is not None:
        parser.error("--output-dir needs the release build; drop --skip-build")
    root = Path(__file__).resolve().parents[1]
    stages = [
        ("Static quality", NOT_RUN),
        ("Release build", "skipped" if args.skip_build else NOT_RUN),
        ("Tests and coverage", NOT_RUN),
    ]
    tests: dict[str, object] | None = None
    with tempfile.TemporaryDirectory(prefix="epg-renderer-release-summary-") as directory:
        summary_path = Path(directory) / "tests.json"
        environment = {**os.environ, SUMMARY_VARIABLE: str(summary_path)}
        ok = _run(root, "Static quality", "-m", "tools.run_quality_checks", environment=environment)
        stages[0] = ("Static quality", PASSED if ok else FAILED)
        if ok and not args.skip_build:
            ok = _build(root, args.output_dir)
            stages[1] = ("Release build", PASSED if ok else FAILED)
        if ok:
            ok = _run(
                root,
                "Tests and coverage",
                "-m",
                "tools.run_coverage_checks",
                environment=environment,
            )
            stages[2] = ("Tests and coverage", PASSED if ok else FAILED)
            tests = _read_test_summary(summary_path)
    print()
    print(format_summary(package_version(root), stages, tests))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
