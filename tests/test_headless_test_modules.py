"""Keep non-GUI test modules importable without Tkinter.

Tests that need Tkinter live in ``test_gui*.py`` modules. Every other test module must
import in a Python without Tkinter, so that parser, model and rendering tests also run
on headless systems instead of failing as a whole module.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
GUI_PREFIX = "test_gui"

_IMPORT_WITHOUT_TKINTER = """
import importlib
import sys

sys.modules["tkinter"] = None
sys.path[:0] = [sys.argv[1], sys.argv[2], sys.argv[3]]
for name in sys.argv[4:]:
    try:
        importlib.import_module(name)
    except Exception as exc:
        print(f"{name}: {type(exc).__name__}: {exc}")
"""


class HeadlessTestModuleTests(unittest.TestCase):
    def test_non_gui_test_modules_import_without_tkinter(self) -> None:
        names = sorted(
            path.stem
            for path in TESTS.glob("test*.py")
            if not path.stem.startswith(GUI_PREFIX) and path.stem != Path(__file__).stem
        )
        self.assertTrue(names)
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                _IMPORT_WITHOUT_TKINTER,
                str(ROOT / "src"),
                str(TESTS),
                str(ROOT),
                *names,
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "", "Move Tkinter-dependent tests to test_gui*.py")


if __name__ == "__main__":
    unittest.main()
