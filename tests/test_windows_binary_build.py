from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.build_windows_binaries import _package_artifacts
from tools.release_tools import DEFAULT_SOURCE_DATE_EPOCH, ReleaseError, is_release_source

ROOT = Path(__file__).resolve().parents[1]


def _fake_windows_dist(root: Path) -> Path:
    dist = root / "dist"
    gui = dist / "EPG-Renderer-GUI"
    internal = gui / "_internal"
    internal.mkdir(parents=True)
    (dist / "epg-render.exe").write_bytes(b"standalone cli")
    (gui / "EPG-Renderer-GUI.exe").write_bytes(b"windowed gui")
    (internal / "python314.dll").write_bytes(b"runtime")
    return dist


class WindowsBinaryBuildTests(unittest.TestCase):
    def test_builder_is_an_explicit_release_source(self):
        self.assertTrue(is_release_source(Path("tools/build_windows_binaries.py")))
        self.assertFalse(is_release_source(Path("tools/build_windows_binaries_2.py")))

    def test_packager_creates_only_the_stable_cli_and_versioned_gui_zip(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            source = workspace / "source"
            source.mkdir()
            (source / "LICENSE").write_bytes(b"BSD 3-Clause test license\n")
            dist = _fake_windows_dist(workspace)
            output = workspace / "release" / "windows"

            artifacts = _package_artifacts(
                source,
                dist,
                output,
                version="1.2.3",
                epoch=DEFAULT_SOURCE_DATE_EPOCH,
            )

            self.assertEqual(artifacts.version, "1.2.3")
            self.assertEqual(artifacts.cli_executable.name, "epg-render.exe")
            self.assertEqual(
                artifacts.gui_archive.name,
                "EPG-Renderer_GUI_Windows_x64_v1.2.3.zip",
            )
            self.assertEqual(
                {path.name for path in output.iterdir()},
                {"epg-render.exe", "EPG-Renderer_GUI_Windows_x64_v1.2.3.zip"},
            )
            self.assertEqual(artifacts.cli_executable.read_bytes(), b"standalone cli")

            with zipfile.ZipFile(artifacts.gui_archive) as archive:
                self.assertEqual(
                    set(archive.namelist()),
                    {
                        "EPG-Renderer-GUI/EPG-Renderer-GUI.exe",
                        "EPG-Renderer-GUI/LICENSE",
                        "EPG-Renderer-GUI/_internal/python314.dll",
                    },
                )
                self.assertEqual(
                    archive.read("EPG-Renderer-GUI/LICENSE"),
                    b"BSD 3-Clause test license\n",
                )
                timestamps = {info.date_time for info in archive.infolist()}
                self.assertEqual(len(timestamps), 1)

    def test_packager_rejects_unexpected_build_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            source = workspace / "source"
            source.mkdir()
            (source / "LICENSE").write_text("license\n", encoding="utf-8")
            dist = _fake_windows_dist(workspace)
            (dist / "unexpected.txt").write_text("stale\n", encoding="utf-8")
            with self.assertRaisesRegex(ReleaseError, "Unexpected Windows build inventory"):
                _package_artifacts(
                    source,
                    dist,
                    workspace / "release",
                    version="1.2.3",
                    epoch=DEFAULT_SOURCE_DATE_EPOCH,
                )

    def test_packager_refuses_a_nonempty_artifact_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            source = workspace / "source"
            source.mkdir()
            (source / "LICENSE").write_text("license\n", encoding="utf-8")
            dist = _fake_windows_dist(workspace)
            output = workspace / "release"
            output.mkdir()
            (output / "stale.zip").write_bytes(b"stale")
            with self.assertRaisesRegex(ReleaseError, "is not empty"):
                _package_artifacts(
                    source,
                    dist,
                    output,
                    version="1.2.3",
                    epoch=DEFAULT_SOURCE_DATE_EPOCH,
                )

    def test_packager_refuses_an_artifact_path_that_is_a_file(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            source = workspace / "source"
            source.mkdir()
            (source / "LICENSE").write_text("license\n", encoding="utf-8")
            dist = _fake_windows_dist(workspace)
            output = workspace / "release"
            output.write_bytes(b"not a directory")
            with self.assertRaisesRegex(ReleaseError, "is not a directory"):
                _package_artifacts(
                    source,
                    dist,
                    output,
                    version="1.2.3",
                    epoch=DEFAULT_SOURCE_DATE_EPOCH,
                )

    def test_ci_builds_extracts_smoke_tests_and_uploads_exact_assets(self):
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        for phrase in (
            "windows-binaries:",
            "runs-on: windows-2022",
            'python-version: "3.14.7"',
            'python -m pip install "pip==26.2.1"',
            "python -m tools.build_windows_binaries --output-dir release/windows",
            "Expand-Archive -LiteralPath $guiZip",
            "python tests/smoke/binary_smoke_test.py",
            '--cli "release\\windows\\epg-render.exe"',
            'EPG-Renderer-GUI\\EPG-Renderer-GUI.exe"',
            "release/windows/epg-render.exe",
            "release/windows/EPG-Renderer_GUI_Windows_x64_v*.zip",
            "if-no-files-found: error",
        ):
            self.assertIn(phrase, workflow)


if __name__ == "__main__":
    unittest.main()
