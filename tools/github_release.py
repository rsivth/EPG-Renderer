"""Assemble the GitHub release assets and extract the release notes."""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path

from tools.release_tools import ReleaseError, sha256_file

CHECKSUM_FILE = "SHA256SUMS.txt"


def changelog_section(changelog: str, heading: str) -> str:
    """Return the body of ``## <heading>`` (optionally dated) up to the next section."""

    pattern = re.compile(
        rf"^## {re.escape(heading)}(?: - \d{{4}}-\d{{2}}-\d{{2}})?\n(?P<body>.*?)(?=^## |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(changelog)
    if match is None:
        raise ReleaseError(f"CHANGELOG.md has no section '## {heading}'.")
    body = match["body"].strip()
    if not body:
        raise ReleaseError(f"CHANGELOG.md section '## {heading}' is empty.")
    return body + "\n"


def _find_one(incoming: Path, pattern: str, label: str) -> Path:
    matches = sorted(path for path in incoming.rglob(pattern) if path.is_file())
    if len(matches) != 1:
        found = ", ".join(str(path.relative_to(incoming)) for path in matches) or "none"
        raise ReleaseError(f"Expected exactly one {label} ({pattern}); found: {found}.")
    return matches[0]


def assemble_release(version: str, incoming: Path, output: Path) -> tuple[Path, ...]:
    """Copy exactly the release assets for ``version`` and write their SHA-256 sums."""

    wanted = (
        (f"EPG-Renderer_GUI_Windows_x64_v{version}.zip", "Windows GUI archive"),
        ("epg-render.exe", "Windows CLI executable"),
        (f"EPG-Renderer_v{version}.zip", "source archive"),
        (f"epg_renderer-{version}-*.whl", "wheel"),
    )
    sources = [_find_one(incoming, pattern, label) for pattern, label in wanted]
    if output.exists() and any(output.iterdir()):
        raise ReleaseError(f"Release asset directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    assets = tuple(Path(shutil.copyfile(source, output / source.name)) for source in sources)
    lines = [f"{sha256_file(asset)}  {asset.name}" for asset in sorted(assets)]
    checksums = output / CHECKSUM_FILE
    checksums.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return (*assets, checksums)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the ``notes`` or ``assemble`` step of the release workflow."""

    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    notes = commands.add_parser("notes", help="Write one CHANGELOG section as release notes")
    notes.add_argument("--changelog", type=Path, default=Path("CHANGELOG.md"))
    notes.add_argument("--heading", required=True, help="Version, or 'Unreleased' for a dry run")
    notes.add_argument("--output", type=Path, required=True)
    assemble = commands.add_parser("assemble", help="Collect the release assets and checksums")
    assemble.add_argument("--version", required=True)
    assemble.add_argument("--input", type=Path, required=True)
    assemble.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "notes":
            text = changelog_section(args.changelog.read_text(encoding="utf-8"), args.heading)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text, encoding="utf-8")
            print(f"Release notes: {args.output}")
        else:
            for asset in assemble_release(args.version, args.input, args.output):
                print(f"Release asset: {asset.name}")
    except (OSError, ReleaseError) as exc:
        print(f"GitHub release step failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
