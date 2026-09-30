"""Regressions for assembling the GitHub release assets and notes.

Until 0.14.0.dev7 a release tag published to PyPI, and the GitHub Release had to be
assembled by hand. Since 0.14.0.dev8 ``tools.github_release`` selects exactly the
release assets, writes ``SHA256SUMS.txt`` and extracts the release notes from the
changelog; missing or ambiguous inputs stop the release before anything is published.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import tempfile
import unittest
from pathlib import Path

from tools.github_release import (
    CHECKSUM_FILE,
    assemble_release,
    changelog_section,
    main,
)
from tools.release_tools import ReleaseError

VERSION = "1.2.3"
CHANGELOG = """# Changelog

## Unreleased

- upcoming change

## 1.2.3 - 2026-10-01

- first change
- second change

## 1.2.2 - 2026-09-01

- older change
"""
ASSETS = {
    "windows/EPG-Renderer_GUI_Windows_x64_v1.2.3.zip": b"gui",
    "windows/epg-render.exe": b"cli",
    "release/EPG-Renderer_v1.2.3.zip": b"source",
    "release/epg_renderer-1.2.3-py3-none-any.whl": b"wheel",
}


def _write_inputs(incoming: Path, files: dict[str, bytes]) -> None:
    for name, payload in files.items():
        path = incoming / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)


class ChangelogSectionTests(unittest.TestCase):
    def test_returns_the_body_of_the_dated_version_section(self) -> None:
        self.assertEqual(changelog_section(CHANGELOG, VERSION), "- first change\n- second change\n")

    def test_returns_the_unreleased_section_for_a_dry_run(self) -> None:
        self.assertEqual(changelog_section(CHANGELOG, "Unreleased"), "- upcoming change\n")

    def test_rejects_a_missing_section(self) -> None:
        with self.assertRaisesRegex(ReleaseError, "## 1.2.4"):
            changelog_section(CHANGELOG, "1.2.4")

    def test_does_not_match_a_longer_version(self) -> None:
        with self.assertRaises(ReleaseError):
            changelog_section(CHANGELOG, "1.2")

    def test_rejects_an_empty_section(self) -> None:
        with self.assertRaisesRegex(ReleaseError, "empty"):
            changelog_section("## 1.2.3\n\n## 1.2.2\n\n- x\n", VERSION)


class AssembleReleaseTests(unittest.TestCase):
    def test_copies_exactly_the_release_assets_and_writes_their_checksums(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            incoming = Path(directory) / "incoming"
            _write_inputs(incoming, {**ASSETS, "release/epg_renderer-1.2.3.tar.gz": b"sdist"})
            output = Path(directory) / "assets"
            assemble_release(VERSION, incoming, output)
            names = sorted(path.name for path in output.iterdir())
            expected = sorted([Path(name).name for name in ASSETS] + [CHECKSUM_FILE])
            self.assertEqual(names, expected)
            lines = (output / CHECKSUM_FILE).read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), len(ASSETS))
            for name, payload in ASSETS.items():
                digest = hashlib.sha256(payload).hexdigest()
                self.assertIn(f"{digest}  {Path(name).name}", lines)
            self.assertEqual(lines, sorted(lines, key=lambda line: line.split("  ", 1)[1]))

    def test_rejects_a_missing_asset(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            incoming = Path(directory) / "incoming"
            _write_inputs(incoming, {k: v for k, v in ASSETS.items() if "exe" not in k})
            with self.assertRaisesRegex(ReleaseError, "epg-render.exe"):
                assemble_release(VERSION, incoming, Path(directory) / "assets")

    def test_rejects_an_ambiguous_asset(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            incoming = Path(directory) / "incoming"
            _write_inputs(incoming, {**ASSETS, "other/epg-render.exe": b"second"})
            with self.assertRaisesRegex(ReleaseError, "epg-render.exe"):
                assemble_release(VERSION, incoming, Path(directory) / "assets")

    def test_rejects_a_wheel_of_another_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            incoming = Path(directory) / "incoming"
            files = {k: v for k, v in ASSETS.items() if not k.endswith(".whl")}
            _write_inputs(incoming, {**files, "release/epg_renderer-1.2.2-py3-none-any.whl": b"w"})
            with self.assertRaisesRegex(ReleaseError, "wheel"):
                assemble_release(VERSION, incoming, Path(directory) / "assets")

    def test_refuses_a_non_empty_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            incoming = Path(directory) / "incoming"
            _write_inputs(incoming, ASSETS)
            output = Path(directory) / "assets"
            output.mkdir()
            (output / "stale.txt").write_text("old", encoding="utf-8")
            with self.assertRaisesRegex(ReleaseError, "not empty"):
                assemble_release(VERSION, incoming, output)


class CommandLineTests(unittest.TestCase):
    def test_notes_command_writes_the_section_and_reports_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            changelog = Path(directory) / "CHANGELOG.md"
            changelog.write_text(CHANGELOG, encoding="utf-8")
            notes = Path(directory) / "notes.md"
            arguments = ["notes", "--changelog", str(changelog), "--output", str(notes)]
            self.assertEqual(main([*arguments, "--heading", VERSION]), 0)
            self.assertEqual(notes.read_text(encoding="utf-8"), "- first change\n- second change\n")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(main([*arguments, "--heading", "9.9.9"]), 1)
            self.assertIn("## 9.9.9", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
