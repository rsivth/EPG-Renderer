from __future__ import annotations

import re
import unittest
from pathlib import Path
from urllib.parse import unquote

import epg_renderer
from epg_renderer.cli import build_parser

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
MARKDOWN_FILES = (ROOT / "README.md", *sorted(DOCS.glob("*.md")))
LOCAL_LINK = re.compile(r"!?\[[^\]]*\]\((?P<target>[^)\s]+)(?:\s+[^)]*)?\)")
MOJIBAKE_MARKERS = ("â€¦", "â€”", "â€", "Ã", "�")


def _local_targets(source: Path) -> tuple[Path, ...]:
    targets: list[Path] = []
    text = source.read_text(encoding="utf-8")
    for match in LOCAL_LINK.finditer(text):
        raw = match.group("target").strip("<>")
        if raw.startswith(("http://", "https://", "mailto:")):
            continue
        path_text = unquote(raw.split("#", 1)[0])
        if path_text:
            targets.append((source.parent / path_text).resolve())
    return tuple(targets)


class DocumentationSiteTests(unittest.TestCase):
    def test_readme_is_a_concise_version_independent_entry_point(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertLessEqual(len(readme.splitlines()), 180)
        self.assertLessEqual(len(readme.split()), 1_100)
        # Since 0.14.0.dev7 installation details live in docs/INSTALLATION.md; since
        # 0.14.0.dev11 the audience routes live in the README's Documentation section.
        for heading in (
            "## Example output",
            "## Capabilities",
            "## Scope and limitations",
            "## Documentation",
        ):
            self.assertIn(heading, readme)
        self.assertIn("docs/index.md", readme)
        self.assertNotRegex(readme, r"\bv\d+\.\d+\.\d+\b")

    def test_documentation_index_exposes_the_primary_user_routes(self) -> None:
        index = (DOCS / "index.md").read_text(encoding="utf-8")
        self.assertTrue(index.startswith("---\n"))
        for target in (
            "GETTING_STARTED.md",
            "CLI.md",
            "PYTHON.md",
            "API.md",
            "GENEMAPPER.md",
            "COORDINATE_MODEL.md",
            "DEVELOPMENT.md",
        ):
            self.assertIn(f"]({target})", index)

    def test_every_local_markdown_link_resolves_inside_the_repository(self) -> None:
        root = ROOT.resolve()
        findings: list[str] = []
        for source in MARKDOWN_FILES:
            for target in _local_targets(source):
                try:
                    target.relative_to(root)
                except ValueError:
                    findings.append(f"{source.relative_to(ROOT)} -> outside repository: {target}")
                    continue
                if not target.exists():
                    findings.append(f"{source.relative_to(ROOT)} -> missing: {target}")
        self.assertEqual(findings, [])

    def test_every_document_page_is_reachable_from_the_index(self) -> None:
        pages = {path.resolve() for path in DOCS.glob("*.md")}
        pending = [DOCS.joinpath("index.md").resolve()]
        reached: set[Path] = set()
        while pending:
            source = pending.pop()
            if source in reached:
                continue
            reached.add(source)
            pending.extend(target for target in _local_targets(source) if target in pages)
        self.assertEqual(pages - reached, set())

    def test_markdown_contains_no_known_mojibake(self) -> None:
        findings: list[str] = []
        for source in MARKDOWN_FILES:
            text = source.read_text(encoding="utf-8")
            for marker in MOJIBAKE_MARKERS:
                if marker in text:
                    findings.append(f"{source.relative_to(ROOT)}: {marker!r}")
        self.assertEqual(findings, [])

    def test_python_vignette_names_every_stable_root_operation(self) -> None:
        vignette = (DOCS / "PYTHON.md").read_text(encoding="utf-8")
        for name in epg_renderer.__all__:
            self.assertIn(name, vignette)

    def test_documented_operation_count_matches_the_package_root(self) -> None:
        words = {7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve"}
        expected = words[len(epg_renderer.__all__) - 1]
        pattern = re.compile(r"\b(" + "|".join(words.values()) + r")\b[^.]*\boperations\b")
        findings: list[str] = []
        for source in MARKDOWN_FILES:
            for match in pattern.finditer(source.read_text(encoding="utf-8")):
                if match.group(1) != expected:
                    findings.append(f"{source.name}: {match.group(0)!r}")
        self.assertEqual(findings, [])

    def test_cli_guide_tracks_every_long_command_option(self) -> None:
        guide = (DOCS / "CLI.md").read_text(encoding="utf-8")
        options = {
            option
            for action in build_parser()._actions
            for option in action.option_strings
            if option.startswith("--")
        }
        for option in options:
            self.assertIn(option, guide)


if __name__ == "__main__":
    unittest.main()
