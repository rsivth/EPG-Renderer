from __future__ import annotations

import ast
import importlib.util
import re
import unittest
from pathlib import Path
from types import ModuleType

from tools.release_tools import is_release_source

ROOT = Path(__file__).resolve().parents[1]
WINDOWS_PACKAGING = ROOT / "packaging" / "windows"
EXPECTED_FILES = {
    "cli_entry.py",
    "epg-render-gui.spec",
    "epg-render.spec",
    "gui_entry.py",
    "requirements.txt",
    "spec_common.py",
}


def _load_spec_common() -> ModuleType:
    module_spec = importlib.util.spec_from_file_location(
        "epg_renderer_windows_spec_common",
        WINDOWS_PACKAGING / "spec_common.py",
    )
    if module_spec is None or module_spec.loader is None:
        raise AssertionError("Could not load the shared Windows spec inputs.")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def _calls(tree: ast.AST, name: str) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name
    ]


def _keyword_constant(call: ast.Call, name: str) -> object:
    for keyword in call.keywords:
        if keyword.arg == name:
            return ast.literal_eval(keyword.value)
    raise AssertionError(f"Missing {name!r} argument.")


class WindowsPackagingTests(unittest.TestCase):
    def test_release_inventory_allows_only_the_canonical_packaging_files(self):
        actual = {path.name for path in WINDOWS_PACKAGING.iterdir() if path.is_file()}
        self.assertEqual(actual, EXPECTED_FILES)
        for name in EXPECTED_FILES:
            with self.subTest(name=name):
                self.assertTrue(is_release_source(Path("packaging/windows") / name))
        self.assertFalse(is_release_source(Path("packaging/windows/local-build.ps1")))
        self.assertFalse(is_release_source(Path("packaging/notes.txt")))

    def test_entry_points_delegate_to_the_public_cli_and_gui_functions(self):
        expected_entry_points = {
            "cli_entry.py": (
                "from epg_renderer.cli import main",
                "raise SystemExit(main())",
            ),
            "gui_entry.py": (
                "from epg_renderer.gui import main",
                "raise SystemExit(_main())",
            ),
        }
        for name, (expected_import, expected_exit) in expected_entry_points.items():
            with self.subTest(name=name):
                source = (WINDOWS_PACKAGING / name).read_text(encoding="utf-8")
                ast.parse(source)
                self.assertIn(expected_import, source)
                self.assertIn(expected_exit, source)

    def test_cli_spec_builds_one_console_executable(self):
        source = (WINDOWS_PACKAGING / "epg-render.spec").read_text(encoding="utf-8")
        tree = ast.parse(source)
        executable_calls = _calls(tree, "EXE")
        self.assertEqual(len(executable_calls), 1)
        self.assertEqual(_keyword_constant(executable_calls[0], "name"), "epg-render")
        self.assertIs(_keyword_constant(executable_calls[0], "console"), True)
        self.assertIs(_keyword_constant(executable_calls[0], "upx"), False)
        self.assertEqual(_calls(tree, "COLLECT"), [])
        self.assertIn('executable_name="epg-render.exe"', source)

    def test_gui_spec_builds_one_windowed_directory_bundle(self):
        source = (WINDOWS_PACKAGING / "epg-render-gui.spec").read_text(encoding="utf-8")
        tree = ast.parse(source)
        executable_calls = _calls(tree, "EXE")
        collect_calls = _calls(tree, "COLLECT")
        self.assertEqual(len(executable_calls), 1)
        self.assertEqual(len(collect_calls), 1)
        self.assertEqual(_keyword_constant(executable_calls[0], "name"), "EPG-Renderer-GUI")
        self.assertIs(_keyword_constant(executable_calls[0], "console"), False)
        self.assertIs(_keyword_constant(executable_calls[0], "exclude_binaries"), True)
        self.assertIs(_keyword_constant(executable_calls[0], "upx"), False)
        self.assertEqual(_keyword_constant(collect_calls[0], "name"), "EPG-Renderer-GUI")
        self.assertIs(_keyword_constant(collect_calls[0], "upx"), False)
        self.assertIn('executable_name="EPG-Renderer-GUI.exe"', source)

    def test_shared_inputs_include_package_data_and_raster_imports(self):
        common = _load_spec_common()
        self.assertEqual(common.HIDDEN_IMPORTS, ["cairosvg", "PIL.Image"])
        self.assertEqual(
            common.PACKAGE_DATA,
            [(str(ROOT / "src" / "epg_renderer" / "data"), "epg_renderer/data")],
        )

    def test_windows_version_tuple_requires_three_numeric_components(self):
        common = _load_spec_common()
        self.assertEqual(common.numeric_windows_version("0.13.37"), (0, 13, 37, 0))
        for invalid in ("0.13", "0.13.37rc1", "0.13.65536"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                common.numeric_windows_version(invalid)

    def test_build_requirements_are_exactly_pinned(self):
        source = (WINDOWS_PACKAGING / "requirements.txt").read_text(encoding="utf-8")
        requirements = {line for line in source.splitlines() if line and not line.startswith("#")}
        self.assertTrue(requirements)
        for requirement in requirements:
            with self.subTest(requirement=requirement):
                self.assertRegex(requirement, re.compile(r"^[A-Za-z0-9_.-]+==[^=<>!~]+$"))
        self.assertIn("pyinstaller==6.22.2", requirements)
        self.assertIn("pyinstaller-hooks-contrib==2026.7", requirements)
        self.assertIn("CairoSVG==2.9.0", requirements)
        self.assertIn("Pillow==12.3.0", requirements)


if __name__ == "__main__":
    unittest.main()
