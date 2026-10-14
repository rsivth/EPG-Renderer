from __future__ import annotations

import ast
import dataclasses
import importlib
import inspect
import unittest
from pathlib import Path

import epg_renderer.batch as batch_module
import epg_renderer.parser as parser_module
import epg_renderer.render_options as options_module

document_module = importlib.import_module("epg_renderer.render_document")
svg_module = importlib.import_module("epg_renderer.render_svg")

ROOT = Path(__file__).resolve().parents[1]


def _function_span(module_path: Path, function_name: str) -> int:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    matches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == function_name
    ]
    if len(matches) != 1:
        raise AssertionError(f"Expected one function named {function_name!r} in {module_path}.")
    node = matches[0]
    assert node.end_lineno is not None
    return node.end_lineno - node.lineno + 1


class RefactoringBoundaryTests(unittest.TestCase):
    def test_public_orchestrators_remain_small(self) -> None:
        source = ROOT / "src" / "epg_renderer"
        limits = {
            ("parser.py", "read_genotypes_table"): 45,
            ("batch.py", "render_genemapper_batch"): 35,
            ("render_options.py", "validate_svg_options"): 40,
            ("render_document.py", "render_positioned_sample_svg"): 25,
        }
        for (file_name, function_name), limit in limits.items():
            with self.subTest(function=function_name):
                self.assertLessEqual(
                    _function_span(source / file_name, function_name),
                    limit,
                )

    def test_parser_delegates_reading_to_the_bundled_strio_reader(self) -> None:
        # Until 0.15.1 parser.py held the reader itself (_ParserConfig, _HeaderLayout,
        # _SampleAccumulator, _parse_marker_row). Since 0.16.0 that structure lives in
        # the bundled STRio package and parser.py only adapts its result.
        source = inspect.getsource(parser_module.read_genotypes_table)
        self.assertIn("strio.read_genemapper", source)
        self.assertIn("max_height=MAX_RFU", source)
        for helper in ("_renderer_error", "_project", "_sample"):
            with self.subTest(helper=helper):
                self.assertTrue(callable(getattr(parser_module, helper)))
        for removed in ("_ParserConfig", "_HeaderLayout", "_SampleAccumulator"):
            with self.subTest(removed=removed):
                self.assertFalse(hasattr(parser_module, removed))

    def test_batch_state_is_owned_by_one_runner(self) -> None:
        self.assertTrue(dataclasses.is_dataclass(batch_module._BatchRequest))
        self.assertTrue(dataclasses.is_dataclass(batch_module._BatchRunner))
        self.assertEqual(
            tuple(inspect.signature(batch_module._BatchRunner._render_sample).parameters),
            ("self", "sample", "path"),
        )

    def test_svg_document_preparation_is_separate_from_channel_drawing(self) -> None:
        self.assertTrue(dataclasses.is_dataclass(document_module._SvgDocumentPlan))
        self.assertEqual(
            tuple(inspect.signature(svg_module._render_channel).parameters),
            ("context",),
        )
        source = inspect.getsource(document_module.render_positioned_sample_svg)
        self.assertIn("_prepare_svg_document", source)
        self.assertIn("_create_svg_document", source)
        self.assertIn("_render_document_channels", source)
        self.assertIn("_render_document_footer", source)

    def test_option_validation_uses_named_validation_steps(self) -> None:
        source = inspect.getsource(options_module.validate_svg_options)
        for helper in (
            "_validate_integer_options",
            "_validate_canvas",
            "_validate_label_area",
            "_validate_boolean_options",
            "_validated_x_domain",
            "_validated_font_family",
        ):
            with self.subTest(helper=helper):
                self.assertIn(helper, source)


if __name__ == "__main__":
    unittest.main()
