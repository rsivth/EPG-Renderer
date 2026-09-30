"""Regressions for documentation statements that must match the code.

Until 0.14.0.dev3 the kit-format guide claimed that bundled profiles are validated
against ``kit_definition_schema.json`` (``kit_schema.py`` validates them; the JSON schema
is not used at runtime) and told contributors to keep complete source exports as
fixtures (the repository holds synthetic data only). The README claimed reproducible
Windows builds (only the source ZIP, sdist and wheel are built twice and compared), and
its Python example used ``render_file``, which returns no parser warnings. Since
0.14.0.dev11 the README has no code; the diagnostics example checked here is the
``render_file_report`` example of the Python vignette.
"""

from __future__ import annotations

import contextlib
import io
import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
PYTHON_VIGNETTE = ROOT / "docs" / "PYTHON.md"
KIT_FORMAT = ROOT / "docs" / "KIT_FORMAT.md"
FIXTURE = ROOT / "tests" / "fixtures" / "globalfiler_minimal.tsv"


def _diagnostics_example() -> str:
    vignette = PYTHON_VIGNETTE.read_text(encoding="utf-8")
    for code in re.findall(r"```python\n(.*?)```", vignette, re.DOTALL):
        if "render_file_report(" in code:
            return code
    raise AssertionError("The Python vignette has no render_file_report example.")


class KitFormatClaimTests(unittest.TestCase):
    def test_kit_format_names_the_loader_that_actually_validates_profiles(self) -> None:
        guide = KIT_FORMAT.read_text(encoding="utf-8")
        self.assertNotRegex(guide, r"validated against `[^`]*kit_definition_schema\.json`")
        self.assertIn("`epg_renderer.kit_schema`", guide)
        self.assertIn("not used at runtime", guide)
        runtime_sources = sorted((ROOT / "src" / "epg_renderer").glob("*.py"))
        self.assertTrue(runtime_sources)
        for source in runtime_sources:
            with self.subTest(source=source.name):
                self.assertNotIn("kit_definition_schema", source.read_text(encoding="utf-8"))

    def test_kit_format_asks_for_synthetic_fixtures_only(self) -> None:
        guide = KIT_FORMAT.read_text(encoding="utf-8")
        self.assertNotIn("retain it unchanged", guide)
        self.assertIn("synthetic", guide)
        self.assertIn("SOURCES.md#test-data-provenance", guide)


class ReadmeClaimTests(unittest.TestCase):
    def test_readme_claims_reproducibility_only_for_artifacts_that_are_compared(self) -> None:
        claims = [line for line in README.read_text("utf-8").splitlines() if "reproducible" in line]
        self.assertTrue(claims)
        for line in claims:
            with self.subTest(line=line):
                self.assertNotIn("Windows", line)
        release_tools = (ROOT / "tools" / "release_tools.py").read_text(encoding="utf-8")
        for artifact in ("source-archive", "source-distribution", "wheel"):
            with self.subTest(artifact=artifact):
                message = f"Two clean {artifact} builds are not byte-reproducible."
                self.assertIn(message, release_tools)

    def test_python_diagnostics_example_reports_diagnostics(self) -> None:
        code = _diagnostics_example()
        self.assertIn("render_file_report(", code)
        self.assertIn("report.messages()", code)

    def test_python_diagnostics_example_runs_on_synthetic_data(self) -> None:
        code = _diagnostics_example()
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            export = workspace / "run.tsv"
            lines = FIXTURE.read_text(encoding="utf-8").splitlines(keepends=True)
            export.write_text(
                "".join(re.sub(r"^S1\t", "DNA-123\t", line) for line in lines),
                encoding="utf-8",
            )
            output = workspace / "sample.svg"
            code = code.replace('"run.tsv"', repr(str(export)))
            code = code.replace('"sample.svg"', repr(str(output)))
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exec(compile(code, "PYTHON.md", "exec"), {})
            self.assertTrue(output.is_file())
            # The synthetic export is complete: no warnings, nothing omitted.
            self.assertEqual(stdout.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
