"""Regressions for the scope of permissive positioning in the rendering workflows.

The rendering workflows check marker names and dyes against the kit before positioning.
Unknown markers and dye conflicts are therefore always rejected there, also with
permissive positioning, and the documentation must say so.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from epg_renderer import render_batch, render_file_report
from epg_renderer.domain import BatchStatus
from epg_renderer.kit_workflow import KitResolutionError

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
KIT = "GlobalFiler"
STATEMENT = "always reject unknown markers and dye conflicts"

DYE_CONFLICT = "Sample Name\tMarker\tDye\tAllele 1\tHeight 1\nS1\tD3S1358\tVIC\t15\t800\n"
UNKNOWN_MARKER = (
    "Sample Name\tMarker\tAllele 1\tHeight 1\nS1\tFOO1\t15\t800\nS1\tD3S1358\t15\t800\n"
)


def _write(directory: Path, text: str) -> Path:
    path = directory / "export.tsv"
    path.write_text(text, encoding="utf-8")
    return path


class PermissiveScopeTests(unittest.TestCase):
    def _assert_rejected(self, text: str, expected: str) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(KitResolutionError, expected):
                render_file_report(
                    _write(root, text), root / "out.svg", kit_name=KIT, strict_positioning=False
                )

    def test_dye_conflict_is_rejected_with_permissive_positioning(self) -> None:
        self._assert_rejected(DYE_CONFLICT, "dye mismatches")

    def test_unknown_marker_is_rejected_with_permissive_positioning(self) -> None:
        self._assert_rejected(UNKNOWN_MARKER, "unknown markers")

    def test_permissive_batch_records_dye_conflict_as_failed_sample(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = render_batch(
                _write(root, DYE_CONFLICT), root / "out", kit_name=KIT, strict_positioning=False
            )
        self.assertEqual([item.status for item in result.items], [BatchStatus.FAILED])

    def test_documentation_states_the_scope_of_permissive_positioning(self) -> None:
        for name in ("COORDINATE_MODEL.md", "CLI.md", "API.md"):
            with self.subTest(document=name):
                text = " ".join((DOCS / name).read_text(encoding="utf-8").split())
                self.assertTrue(STATEMENT in text, f"{name} must state: {STATEMENT}")


if __name__ == "__main__":
    unittest.main()
