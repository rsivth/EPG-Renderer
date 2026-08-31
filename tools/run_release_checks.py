"""Run the complete release gate without repeating the full test suite."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

from tools.release_tools import ReleaseError, build_reproducible_release


def _run(root: Path, label: str, *arguments: str) -> bool:
    print(f"\n== {label} ==", flush=True)
    result = subprocess.run([sys.executable, *arguments], cwd=root, check=False)
    print(f"{label}: {'passed' if result.returncode == 0 else 'failed'}", flush=True)
    return result.returncode == 0


def main() -> int:
    """Run static checks, the reproducible build, and one covered test run."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="retain the fully verified release artifacts in this directory",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if not _run(root, "Static quality", "-m", "tools.run_quality_checks"):
        print("All release checks passed: no")
        return 1

    print("\n== Reproducible release ==", flush=True)
    try:
        if args.output_dir is None:
            with tempfile.TemporaryDirectory(prefix="epg-renderer-release-check-") as directory:
                build_reproducible_release(root, Path(directory))
        else:
            build_reproducible_release(root, args.output_dir.resolve())
    except ReleaseError as exc:
        print(f"Reproducible release: failed\n{exc}")
        print("All release checks passed: no")
        return 1
    print("Reproducible release: passed")

    if not _run(root, "Tests and coverage", "-m", "tools.run_coverage_checks"):
        print("All release checks passed: no")
        return 1
    print("All release checks passed: yes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
