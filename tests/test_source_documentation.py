"""Regression tests for production source-code documentation."""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_PACKAGE = _ROOT / "src" / "epg_renderer"
_STALE_COMMENTARY = re.compile(
    r"(?:v0\.\d|historical|legacy|compatibility hook|for tests?|test-only)",
    re.IGNORECASE,
)


class SourceDocumentationTests(unittest.TestCase):
    """Keep production documentation complete and focused on current contracts."""

    def test_every_production_module_has_a_docstring(self) -> None:
        """Require a module docstring in every production Python file."""
        missing: list[str] = []
        for path in sorted(_PACKAGE.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            if ast.get_docstring(tree, clean=False) is None:
                missing.append(path.name)
        self.assertEqual(missing, [])

    def test_public_objects_have_docstrings(self) -> None:
        """Require documentation for every non-private class, function and method."""
        missing: list[str] = []
        for path in sorted(_PACKAGE.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                if node.name.startswith("_"):
                    continue
                if any(
                    isinstance(decorator, ast.Name) and decorator.id == "overload"
                    for decorator in node.decorator_list
                ):
                    continue
                if ast.get_docstring(node, clean=False) is None:
                    missing.append(f"{path.name}:{node.lineno}:{node.name}")
        self.assertEqual(missing, [])

    def test_production_docstrings_do_not_contain_stale_commentary(self) -> None:
        """Keep release history and test rationale out of production documentation."""
        findings: list[str] = []
        for path in sorted(_PACKAGE.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            documentable = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
            for node in ast.walk(tree):
                if not isinstance(node, documentable):
                    continue
                docstring = ast.get_docstring(node, clean=False)
                if docstring and _STALE_COMMENTARY.search(docstring):
                    findings.append(f"{path.name}:{getattr(node, 'lineno', 1)}")
        self.assertEqual(findings, [])

    def test_pydocstyle_rules_are_part_of_the_ruff_gate(self) -> None:
        """Prevent accidental removal of the documentation lint rules."""
        configuration = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertRegex(configuration, r'(?m)^\s*"D",\s*$')

    def test_pydocstyle_is_not_blanket_disabled(self) -> None:
        """Keep documentation linting active for production and tool modules."""
        configuration = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertNotRegex(configuration, r'(?m)^\s*"\*\.py"\s*=\s*\[[^\]]*"D"')


if __name__ == "__main__":
    unittest.main()
