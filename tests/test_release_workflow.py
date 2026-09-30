"""Regressions for the GitHub release workflow.

Until 0.14.0.dev7 a version tag started publish-pypi.yml, which uploaded to TestPyPI
and PyPI, while the GitHub Release had to be created by hand and the Windows build
steps existed only in ci.yml. PyPI publication is deferred since 0.14.0.dev8:
release.yml builds and verifies the sources and the Windows programs, assembles the
assets and creates the GitHub Release for a version tag. A manual run produces only
the preview artifact. Only the tag-triggered release job may write to the repository.
"""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
RELEASE = WORKFLOWS / "release.yml"
WINDOWS = WORKFLOWS / "windows-binaries.yml"
CI = WORKFLOWS / "ci.yml"
TAG_ONLY = "if: github.event_name == 'push' && github.ref_type == 'tag'"


def _job(source: str, name: str) -> str:
    match = re.search(
        rf"^  {re.escape(name)}:\n(?P<body>.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)",
        source,
        re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"Job {name!r} is missing.")
    return match["body"]


class ReleaseWorkflowTests(unittest.TestCase):
    def test_no_workflow_publishes_to_pypi(self) -> None:
        self.assertFalse((WORKFLOWS / "publish-pypi.yml").exists())
        for workflow in sorted(WORKFLOWS.glob("*.yml")):
            with self.subTest(workflow=workflow.name):
                self.assertNotIn("pypi", workflow.read_text(encoding="utf-8").casefold())

    def test_windows_build_is_defined_once_and_used_by_ci_and_release(self) -> None:
        windows = WINDOWS.read_text(encoding="utf-8")
        self.assertIn("on:\n  workflow_call:", windows)
        self.assertIn("runs-on: windows-2022", windows)
        for caller in (CI, RELEASE):
            with self.subTest(workflow=caller.name):
                source = caller.read_text(encoding="utf-8")
                self.assertIn("uses: ./.github/workflows/windows-binaries.yml", source)
                self.assertNotIn("windows-2022", source)

    def test_only_the_tag_triggered_release_job_can_write(self) -> None:
        writers = {
            workflow.name: workflow.read_text(encoding="utf-8").count("contents: write")
            for workflow in WORKFLOWS.glob("*.yml")
        }
        self.assertEqual(
            {name: count for name, count in writers.items() if count}, {"release.yml": 1}
        )
        release = RELEASE.read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", release)
        job = _job(release, "github-release")
        self.assertIn("contents: write", job)
        self.assertIn(TAG_ONLY, job)
        self.assertNotIn("secrets.", release)

    def test_release_is_gated_on_version_notes_and_verified_assets(self) -> None:
        release = RELEASE.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", release)
        self.assertIn('tags:\n      - "v*"', release)
        build = _job(release, "build")
        for phrase in (
            '"$GITHUB_REF_NAME" != "v$version"',
            "python -m tools.github_release notes",
            "python -m tools.run_release_checks --output-dir release",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, build)
        assemble = _job(release, "assemble")
        self.assertIn("needs: [build, windows]", assemble)
        self.assertIn("python -m tools.github_release assemble", assemble)
        self.assertIn("name: release-preview", assemble)
        publish = _job(release, "github-release")
        self.assertIn("needs: [build, assemble]", publish)
        for phrase in ('gh release create "$GITHUB_REF_NAME"', "--verify-tag", "--notes-file"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, publish)


class ReleaseNotesLocationTests(unittest.TestCase):
    """0.14.0.dev8 wrote the notes into notes/ before the release gate, which rejects
    every unapproved file in the source tree; the dry run failed there."""

    def test_notes_are_written_outside_the_checked_source_tree(self) -> None:
        build = _job(RELEASE.read_text(encoding="utf-8"), "build")
        self.assertNotIn("notes/release-notes.md", build)
        self.assertIn('--output "$RUNNER_TEMP/release-notes.md"', build)
        gate = build.index("python -m tools.run_release_checks --output-dir release")
        copy = build.index('cp "$RUNNER_TEMP/release-notes.md" release/release-notes.md')
        self.assertLess(gate, copy)

    def test_release_gate_ignores_its_output_directory_but_not_other_new_files(self) -> None:
        from tools.release_tools import unexpected_release_paths

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("notes/release-notes.md", "release/release-notes.md"):
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_text("- change\n", encoding="utf-8")
            self.assertEqual(unexpected_release_paths(root), (Path("notes/release-notes.md"),))


if __name__ == "__main__":
    unittest.main()
