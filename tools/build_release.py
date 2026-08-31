"""Build the reproducible EPG-Renderer source ZIP, sdist, and wheel."""

from __future__ import annotations

import argparse
from pathlib import Path

from tools.release_tools import DEFAULT_SOURCE_DATE_EPOCH, ReleaseError, build_reproducible_release


def main() -> int:
    """Build and report one verified reproducible release."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("release"))
    parser.add_argument("--source-date-epoch", type=int, default=DEFAULT_SOURCE_DATE_EPOCH)
    parser.add_argument("--skip-smoke-test", action="store_true")
    parser.add_argument("--skip-source-test", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        artifacts = build_reproducible_release(
            root,
            args.output_dir.resolve(),
            epoch=args.source_date_epoch,
            smoke_test=not args.skip_smoke_test,
            source_test=not args.skip_source_test,
        )
    except ReleaseError as exc:
        print(f"Release build failed: {exc}")
        return 1
    print(f"Version: {artifacts.version}")
    print(f"Source archive: {artifacts.source_archive}")
    print(f"Source SHA-256: {artifacts.source_digest}")
    print(f"Source distribution: {artifacts.sdist}")
    print(f"Source-distribution SHA-256: {artifacts.sdist_digest}")
    print(f"Wheel: {artifacts.wheel}")
    print(f"Wheel SHA-256: {artifacts.wheel_digest}")
    print("Reproducible release build: yes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
