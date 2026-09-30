from __future__ import annotations

import io
import re
import tarfile
import tempfile
import unittest
from pathlib import Path

import tools.release_tools as release_tools
from tools.release_tools import ReleaseError

ROOT = Path(__file__).resolve().parents[1]


def _raw_sdist(path: Path, names: tuple[str, ...], *, mtime: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(path, mode="w:gz") as archive:
        for name in names:
            member = tarfile.TarInfo(name)
            member.mtime = mtime
            if name.endswith("/"):
                member.type = tarfile.DIRTYPE
                member.mode = 0o700
                archive.addfile(member)
                continue
            payload = f"payload for {name}\n".encode()
            member.mode = 0o600
            member.size = len(payload)
            archive.addfile(member, io.BytesIO(payload))


class PyProjectMetadataTests(unittest.TestCase):
    def test_project_declares_complete_pypi_metadata(self) -> None:
        source = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        for phrase in (
            'readme = "README.md"',
            'license = "BSD-3-Clause"',
            'license-files = ["LICENSE"]',
            "maintainers = [",
            '{name = "rsivth"}',
            '"Development Status :: 4 - Beta"',
            '"Operating System :: OS Independent"',
            '"Programming Language :: Python :: 3.10"',
            '"Programming Language :: Python :: 3.14"',
            '"Topic :: Scientific/Engineering :: Bio-Informatics"',
            '"Topic :: Scientific/Engineering :: Visualization"',
            "[project.urls]",
            'Documentation = "https://github.com/rsivth/EPG-Renderer/blob/main/docs/index.md"',
            'Changelog = "https://github.com/rsivth/EPG-Renderer/blob/main/CHANGELOG.md"',
            '"twine==7.0.0"',
        ):
            self.assertIn(phrase, source)

    def test_public_readme_uses_absolute_project_links(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        # Until 0.14.0.dev9 the README installed the unowned PyPI name epg-renderer.
        # Since 0.14.0.dev10 it points to the installation guide's release-wheel
        # command; the README is also the wheel's long description and needs
        # absolute links.
        self.assertIn(
            "https://github.com/rsivth/EPG-Renderer/blob/main/docs/INSTALLATION.md#python-package",
            readme,
        )
        for target in re.findall(r"!?\[[^]]*\]\(([^)\s]+)", readme):
            self.assertTrue(
                target.startswith("https://"),
                f"PyPI README link must be absolute: {target}",
            )


class SourceDistributionTests(unittest.TestCase):
    def test_sdist_normalization_removes_backend_order_and_timestamp_variation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            names = ("epg_renderer-1.2.3/", "epg_renderer-1.2.3/PKG-INFO")
            first_raw = root / "first-raw.tar.gz"
            second_raw = root / "second-raw.tar.gz"
            _raw_sdist(first_raw, names, mtime=1_000)
            _raw_sdist(second_raw, tuple(reversed(names)), mtime=2_000)
            first = root / "first.tar.gz"
            second = root / "second.tar.gz"

            release_tools._normalize_sdist(first_raw, first, epoch=1784592000)
            release_tools._normalize_sdist(second_raw, second, epoch=1784592000)

            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_sdist_normalization_rejects_links(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "unsafe.tar.gz"
            with tarfile.open(raw, mode="w:gz") as archive:
                member = tarfile.TarInfo("epg_renderer-1.2.3/link")
                member.type = tarfile.SYMTYPE
                member.linkname = "../../outside"
                archive.addfile(member)
            with self.assertRaisesRegex(ReleaseError, "Unsupported.*member type"):
                release_tools._normalize_sdist(raw, root / "normalized.tar.gz", epoch=1)

    def test_release_gate_builds_and_checks_both_python_distribution_formats(self) -> None:
        source = (ROOT / "tools/release_tools.py").read_text(encoding="utf-8")
        for phrase in (
            "def inspect_sdist(",
            "def check_distributions(",
            "def test_sdist_installation(",
            '"twine", "check", "--strict"',
            "Two clean source-distribution builds are not byte-reproducible.",
            "test_sdist_installation(sdist_target",
        ):
            self.assertIn(phrase, source)
        runner = (ROOT / "tools/run_release_checks.py").read_text(encoding="utf-8")
        self.assertIn('"--output-dir"', runner)


class ReleaseWorkflowPrivilegeTests(unittest.TestCase):
    """Former PyPI publication checks, carried over to release.yml in 0.14.0.dev8.

    PyPI publication is deferred; the intent of these tests remains: least privilege,
    validation before publication, and pinned external actions.
    """

    def setUp(self) -> None:
        self.source = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    def test_workflow_uses_least_privilege(self) -> None:
        self.assertIn("permissions:\n  contents: read", self.source)
        self.assertEqual(self.source.count("contents: write"), 1)
        self.assertNotIn("id-token: write", self.source)
        self.assertNotIn("secrets.", self.source)
        self.assertNotIn("api-token", self.source.casefold())

    def test_workflow_validates_everything_before_publication(self) -> None:
        for phrase in (
            "if: github.event_name == 'push' && github.ref_type == 'tag'",
            '"$GITHUB_REF_NAME" != "v$version"',
            "A manual dry run must start from the default branch.",
            "python -m tools.run_release_checks --output-dir release",
            "needs: [build, windows]",
            "needs: [build, assemble]",
        ):
            self.assertIn(phrase, self.source)

    def test_every_external_action_is_pinned_to_a_full_commit(self) -> None:
        action_lines = [
            line.strip().removeprefix("- ")
            for line in self.source.splitlines()
            if "uses:" in line and "uses: ./" not in line
        ]
        self.assertGreaterEqual(len(action_lines), 6)
        for line in action_lines:
            with self.subTest(line=line):
                self.assertRegex(line, r"^uses: [^@]+@[0-9a-f]{40}(?: # .+)?$")


if __name__ == "__main__":
    unittest.main()
