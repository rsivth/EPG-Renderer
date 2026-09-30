"""Regressions for the versions accepted by the Windows binary smoke test.

In 0.14.0.dev1 the Windows build accepted the development version, but the smoke
runner still required exactly three numeric parts and stopped before running any
binary. Every Windows release check must accept the version the repository carries,
and the build and the smoke runner must agree on the accepted formats.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path
from types import ModuleType

from tools.release_tools import project_version

ROOT = Path(__file__).resolve().parents[1]
SMOKE_PATH = ROOT / "tests" / "smoke" / "binary_smoke_test.py"
SPEC_COMMON_PATH = ROOT / "packaging" / "windows" / "spec_common.py"
FIXTURE = ROOT / "tests" / "fixtures" / "globalfiler_minimal.tsv"

VALID_VERSIONS = ("1.2.3", "0.13.37", "0.14.0.dev1", "0.14.0.dev12", "0.14.0rc2")
# The 65535 component limit is a Windows file-version rule; the build enforces it
# before the smoke test runs, so it is not part of the shared format list.
INVALID_VERSIONS = (
    "",
    "0.13",
    "0.14.0.dev",
    "0.14.0a1",
    "0.14.0.post1",
    "0.14.0-dev1",
    "v0.14.0",
    " 0.14.0",
    "0.14.0.dev1\n",
)


def _load(path: Path, name: str) -> ModuleType:
    module_spec = importlib.util.spec_from_file_location(name, path)
    if module_spec is None or module_spec.loader is None:
        raise AssertionError(f"Could not load {path.name}.")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


class BinarySmokeVersionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.smoke = _load(SMOKE_PATH, "epg_renderer_binary_smoke_versions")
        self.spec_common = _load(SPEC_COMMON_PATH, "epg_renderer_spec_common_versions")

    def test_smoke_runner_accepts_the_development_version_that_failed_in_ci(self) -> None:
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            tempfile.TemporaryDirectory() as directory,
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            status = self.smoke.main(
                [
                    "--cli",
                    str(Path(directory) / "missing-epg-render.exe"),
                    "--gui",
                    str(Path(directory) / "missing-EPG-Renderer-GUI.exe"),
                    "--fixture",
                    str(FIXTURE),
                    "--expected-version",
                    "0.14.0.dev1",
                ]
            )
        # The version check must pass; the run then stops at the missing executable.
        self.assertEqual(status, 1)
        self.assertNotIn("Expected version", stderr.getvalue())
        self.assertIn("CLI executable is missing", stderr.getvalue())

    def test_every_windows_release_check_accepts_the_current_project_version(self) -> None:
        version = project_version(ROOT)
        self.spec_common.numeric_windows_version(version)
        self.smoke._check_expected_version(version)

    def test_build_and_smoke_runner_accept_the_same_version_formats(self) -> None:
        for version in VALID_VERSIONS:
            with self.subTest(valid=version):
                self.spec_common.numeric_windows_version(version)
                self.smoke._check_expected_version(version)
        for version in INVALID_VERSIONS:
            with self.subTest(invalid=version):
                with self.assertRaises(ValueError):
                    self.spec_common.numeric_windows_version(version)
                with self.assertRaises(self.smoke.BinarySmokeError):
                    self.smoke._check_expected_version(version)


if __name__ == "__main__":
    unittest.main()
