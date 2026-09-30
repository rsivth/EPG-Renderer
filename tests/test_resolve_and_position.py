"""Regressions for the single kit-resolution-then-positioning step of the workflows.

The rendering workflows first resolve a kit with the explicit-kit compatibility checks
and then position the sample. That rule lives in ``resolve_and_position``; the kit is
scored once, and the result equals the former two-step sequence.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path
from unittest import mock

from epg_renderer import kit_workflow, load_project, render_svg
from epg_renderer.kit_workflow import KitResolutionError, position_sample, resolve_kit
from epg_renderer.models import AlleleCall, MarkerCall, SampleCall

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "epg_renderer"
FIXTURES = ROOT / "tests" / "fixtures"
KIT = "GlobalFiler"

# Modules that may call resolve_kit directly: its definition, the GUI kit preview, and
# the batch runner, which checks for one common kit between resolving and positioning.
RESOLVE_KIT_CALLERS = frozenset({"kit_workflow.py", "gui_workflow.py", "batch.py"})


def _dye_conflict_sample() -> SampleCall:
    call = AlleleCall(1, "15", 800)
    return SampleCall("S1", {"D3S1358": MarkerCall("D3S1358", "VIC", (call,))})


def _fixture_samples() -> list[SampleCall]:
    samples: list[SampleCall] = []
    for name in ("globalfiler_minimal.tsv", "ngm_minimal.tsv", "esi17_two_person_mixture.tsv"):
        project = load_project(FIXTURES / name)
        samples.extend(project.sample(sample_id) for sample_id in project.sample_ids)
    return samples


class ResolveAndPositionTests(unittest.TestCase):
    def test_result_equals_the_former_two_step_sequence(self) -> None:
        for sample in _fixture_samples():
            for kit_name in (None, resolve_kit(sample).kit.name):
                with self.subTest(sample=sample.sample_id, kit=kit_name):
                    expected = position_sample(
                        sample, kit_name=resolve_kit(sample, kit_name=kit_name).kit.name
                    )
                    actual = kit_workflow.resolve_and_position(sample, kit_name=kit_name)
                    self.assertEqual(actual, expected)

    def test_explicit_kit_conflict_is_rejected_in_permissive_mode(self) -> None:
        with self.assertRaisesRegex(KitResolutionError, "dye mismatches"):
            kit_workflow.resolve_and_position(_dye_conflict_sample(), kit_name=KIT, strict=False)

    def test_kit_is_scored_once_for_an_explicit_kit(self) -> None:
        sample = load_project(FIXTURES / "globalfiler_minimal.tsv").sample("S1")
        with mock.patch.object(
            kit_workflow, "_score_profile", wraps=kit_workflow._score_profile
        ) as score:
            kit_workflow.resolve_and_position(sample, kit_name=KIT)
        self.assertEqual(score.call_count, 1)

    def test_render_svg_rejects_explicit_kit_conflict_in_permissive_mode(self) -> None:
        with self.assertRaisesRegex(KitResolutionError, "dye mismatches"):
            render_svg(_dye_conflict_sample(), kit_name=KIT, strict_positioning=False)

    def test_only_designated_modules_call_resolve_kit(self) -> None:
        callers: set[str] = set()
        for path in sorted(PACKAGE.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "resolve_kit"
                ):
                    callers.add(path.name)
        self.assertEqual(callers - RESOLVE_KIT_CALLERS, set())


if __name__ == "__main__":
    unittest.main()
