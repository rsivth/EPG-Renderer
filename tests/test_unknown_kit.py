"""Regressions for unknown kit names supplied by users.

An unknown ``--kit`` value is a user input error. The CLI must report it as a normal
error message with exit status 2 instead of terminating with a Python traceback.
"""

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from epg_renderer.cli import main as cli_main
from epg_renderer.kit_registry import get_kit_profile

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "globalfiler_minimal.tsv"
UNKNOWN = "Foo"


def _run_cli(*arguments: str) -> tuple[int, str]:
    stderr = io.StringIO()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(stderr):
        status = cli_main(list(arguments))
    return status, stderr.getvalue()


class UnknownKitTests(unittest.TestCase):
    def test_lookup_error_is_a_readable_value_error_and_remains_a_key_error(self) -> None:
        with self.assertRaises(ValueError) as context:
            get_kit_profile(UNKNOWN)
        self.assertIsInstance(context.exception, KeyError)
        message = str(context.exception)
        self.assertTrue(message.startswith(f"Unknown kit {UNKNOWN!r}."), message)
        self.assertIn("GlobalFiler", message)

    def test_single_render_cli_reports_unknown_kit_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            status, stderr = _run_cli(
                str(FIXTURE), str(Path(directory) / "out.svg"), "--kit", UNKNOWN
            )
        self.assertEqual(status, 2, stderr)
        self.assertIn(f"epg-render: error: Unknown kit {UNKNOWN!r}.", stderr)

    def test_batch_cli_reports_unknown_kit_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            status, stderr = _run_cli(
                str(FIXTURE), str(Path(directory) / "out"), "--all-samples", "--kit", UNKNOWN
            )
        self.assertEqual(status, 2, stderr)
        self.assertIn(f"Unknown kit {UNKNOWN!r}.", stderr)


if __name__ == "__main__":
    unittest.main()
