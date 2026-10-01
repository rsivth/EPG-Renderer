"""Regressions for the published shape of CHANGELOG.md.

Until 0.14.0.dev16 the changelog held one section per internal development version,
from 0.1.0 to 0.13.49, none of which was ever published, plus an `## Unreleased`
section written per development version. The release workflow turns the top section
into the GitHub release text, so the 0.14.0.dev16 dry run produced release notes made
of internal development steps. Since 0.14.0.dev17 the top section describes the
release for its readers, development versions are not cited (the Git history keeps
them), and the unpublished versions are summarized in one closing sentence.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from tools.github_release import changelog_section

ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
HEADINGS = re.findall(r"^## (.+)$", CHANGELOG, re.MULTILINE)
EARLIER = "Earlier development versions"


class ChangelogShapeTests(unittest.TestCase):
    def test_changelog_cites_no_development_versions(self) -> None:
        self.assertEqual(re.findall(r"\d+\.\d+\.\d+\.dev\d+", CHANGELOG), [])

    def test_changelog_has_no_sections_for_unpublished_versions(self) -> None:
        self.assertEqual(len(HEADINGS), len(set(HEADINGS)))
        self.assertEqual(HEADINGS[-1], EARLIER)
        for heading in HEADINGS:
            with self.subTest(heading=heading):
                self.assertNotRegex(heading, r"^0\.(\d|1[0-3])\.\d+\b")
        self.assertIn("0.1.0", _section(EARLIER))
        self.assertIn("were not published", _section(EARLIER))

    def test_first_release_section_is_release_text_for_users(self) -> None:
        # The 0.14.0 section, or the Unreleased section before it is renamed.
        released = [h.split(" - ", 1)[0] for h in HEADINGS if h.startswith("0.14.0")]
        notes = changelog_section(CHANGELOG, released[0] if released else "Unreleased")
        for phrase in ("first public release", "EPG-Renderer-GUI.exe", "wheel", "SHA256SUMS"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, notes)

    def test_top_section_matches_the_package_version(self) -> None:
        # A final version needs its dated section before the tag is pushed; a
        # development version collects changes under Unreleased.
        version = re.search(
            r'^__version__ = "([^"]+)"$',
            (ROOT / "src" / "epg_renderer" / "version.py").read_text(encoding="utf-8"),
            re.MULTILINE,
        )
        assert version is not None
        if ".dev" in version[1]:
            self.assertEqual(HEADINGS[0], "Unreleased")
        else:
            self.assertRegex(HEADINGS[0], rf"^{re.escape(version[1])} - \d{{4}}-\d{{2}}-\d{{2}}$")


def _section(heading: str) -> str:
    section = CHANGELOG.split(f"## {heading}\n", 1)[1].split("\n## ", 1)[0]
    return " ".join(section.split())


if __name__ == "__main__":
    unittest.main()
