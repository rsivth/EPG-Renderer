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

    def test_parser_has_explicit_configuration_header_and_accumulator_types(self) -> None:
        for model in (
            parser_module._ParserConfig,
            parser_module._HeaderLayout,
            parser_module._SampleAccumulator,
        ):
            with self.subTest(model=model.__name__):
                self.assertTrue(dataclasses.is_dataclass(model))
        self.assertEqual(
            tuple(inspect.signature(parser_module._parse_marker_row).parameters),
            ("raw", "line_number", "layout", "require_height"),
        )

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
