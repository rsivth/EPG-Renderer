"""Regression tests for the unpacked-source GUI launcher."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class OfflineLauncherTests(unittest.TestCase):
    """Verify that the unpacked source archive starts without installation."""

    def test_launcher_check_works_without_pythonpath(self) -> None:
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        result = subprocess.run(
            [sys.executable, str(ROOT / "launch_gui.py"), "--check"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("offline GUI launcher is ready", result.stdout)

    def test_python_launcher_can_show_errors_without_console(self) -> None:
        launcher = (ROOT / "launch_gui.py").read_text(encoding="utf-8")
        self.assertIn("MessageBoxW", launcher)
        self.assertIn("sys.stderr", launcher)

    def test_release_inventory_contains_only_the_python_launcher(self) -> None:
        from tools.release_tools import is_release_source

        self.assertTrue(is_release_source(Path("launch_gui.py")))
        self.assertFalse(is_release_source(Path("START_GUI.vbs")))
        self.assertFalse(is_release_source(Path("START_GUI_CMD_FALLBACK.bat")))
        self.assertFalse((ROOT / "START_GUI.vbs").exists())
        self.assertFalse((ROOT / "START_GUI_CMD_FALLBACK.bat").exists())


if __name__ == "__main__":
    unittest.main()
