from __future__ import annotations

import ast
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import epg_renderer.render_io as render_io
from epg_renderer.kit_schema import KitSchemaError, profile_from_payload
from epg_renderer.render_options import RasterRenderError, SvgRenderError

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).with_name("fixtures") / "globalfiler_minimal.tsv"


class StaticQualityTests(unittest.TestCase):
    def test_pyproject_defines_reproducible_quality_gates(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        for phrase in (
            "dev = [",
            '"mypy==1.18.2"',
            '"ruff==0.12.12"',
            "[tool.ruff]",
            'target-version = "py310"',
            "[tool.mypy]",
            "strict = true",
            'files = ["src/epg_renderer"]',
        ):
            self.assertIn(phrase, pyproject)

    def test_quality_runner_covers_lint_format_types_and_compilation(self):
        source = (ROOT / "tools" / "run_quality_checks.py").read_text(encoding="utf-8")
        for phrase in ("Ruff lint", "Ruff format", "MyPy strict", "Compileall"):
            self.assertIn(phrase, source)
        self.assertIn('("src", "tests", "examples"', source)
        ast.parse(source)

    def test_quality_runner_includes_source_launcher(self):
        source = (ROOT / "tools" / "run_quality_checks.py").read_text(encoding="utf-8")
        self.assertIn('"launch_gui.py"', source)

    def test_package_source_has_no_type_ignore_directives(self):
        offenders = []
        for path in (ROOT / "src" / "epg_renderer").glob("*.py"):
            if "type: ignore" in path.read_text(encoding="utf-8"):
                offenders.append(path.name)
        self.assertEqual(offenders, [])

    def test_broad_exception_handlers_are_limited_to_real_boundaries(self):
        allowed = {
            ("batch.py", "_render_one_sample"),
            ("gui.py", "choose_input"),
            ("gui.py", "create_image"),
            ("render_io.py", "write_raster_image"),
        }
        found: set[tuple[str, str]] = set()
        for path in (ROOT / "src" / "epg_renderer").glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))

            class Visitor(ast.NodeVisitor):
                def __init__(self, file_name: str) -> None:
                    self.file_name = file_name
                    self.parents: list[str] = []

                def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                    self.parents.append(node.name)
                    self.generic_visit(node)
                    self.parents.pop()

                visit_AsyncFunctionDef = visit_FunctionDef

                def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
                    if isinstance(node.type, ast.Name) and node.type.id == "Exception":
                        found.add((self.file_name, self.parents[-1]))
                    self.generic_visit(node)

            Visitor(path.name).visit(tree)
        self.assertEqual(found, allowed)


class BoundaryRobustnessTests(unittest.TestCase):
    def test_schema_rejects_non_string_object_keys(self):
        payload = json.loads(
            (ROOT / "src" / "epg_renderer" / "data" / "kits" / "globalfiler_v1.json").read_text(
                encoding="utf-8"
            )
        )
        payload[1] = "invalid JSON-style key"
        with self.assertRaisesRegex(KitSchemaError, "string object keys"):
            profile_from_payload(payload)

    def test_svg_writer_wraps_parent_directory_creation_errors(self):
        svg = (ROOT / "examples" / "globalfiler_example.svg").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as directory:
            blocker = Path(directory) / "not-a-directory"
            blocker.write_text("file", encoding="utf-8")
            with self.assertRaises(SvgRenderError) as raised:
                render_io.write_svg(svg, blocker / "out.svg")
        self.assertIsInstance(raised.exception.__cause__, OSError)

    def test_binary_writer_wraps_parent_directory_creation_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            blocker = Path(directory) / "not-a-directory"
            blocker.write_text("file", encoding="utf-8")
            with self.assertRaises(RasterRenderError) as raised:
                render_io._atomic_write_bytes(blocker / "out.png", b"data")
        self.assertIsInstance(raised.exception.__cause__, OSError)

    def test_rasterizer_rejects_missing_byte_result(self):
        svg = (ROOT / "examples" / "globalfiler_example.svg").read_text(encoding="utf-8")
        cairo = mock.Mock()
        cairo.svg2png.return_value = None
        image_module = mock.Mock()
        with (
            tempfile.TemporaryDirectory() as directory,
            mock.patch.object(
                render_io, "_load_raster_dependencies", return_value=(cairo, image_module)
            ),
            self.assertRaisesRegex(RasterRenderError, "did not return PNG bytes"),
        ):
            render_io.write_raster_image(svg, Path(directory) / "out.png")


if __name__ == "__main__":
    unittest.main()
