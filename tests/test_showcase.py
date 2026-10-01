"""Regressions for the showcase figure and the page that explains it.

Until 0.14.0 the documentation described in words only how unusual calls appear in a
figure. Since 0.15.0.dev1 a synthetic NGM export with such calls is rendered as a
committed example, and docs/READING_THE_FIGURE.md explains every case it shows: an
off-ladder call with an exported size, an off-ladder call without a size, a numeric
allele outside the ladder, microvariants and a homozygous marker.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "ngm_showcase.tsv"
EXAMPLE = ROOT / "examples" / "ngm_showcase_example.svg"
PAGE = ROOT / "docs" / "READING_THE_FIGURE.md"
PAGE_URL = "https://github.com/rsivth/EPG-Renderer/blob/main/docs/READING_THE_FIGURE.md"


def _peaks(svg: str, marker: str) -> list[str]:
    return re.findall(rf'<g class="called-peak"[^>]*data-marker="{marker}"[^>]*>', svg)


class ShowcaseFigureTests(unittest.TestCase):
    def test_showcase_figure_contains_every_explained_case(self) -> None:
        svg = EXAMPLE.read_text(encoding="utf-8")
        ol_with_size = [p for p in _peaks(svg, "D21S11") if 'data-allele="OL"' in p]
        self.assertEqual(len(ol_with_size), 1)
        self.assertIn('data-coordinate-source="measured"', ol_with_size[0])
        estimated = [p for p in _peaks(svg, "vWA") if 'data-allele="25"' in p]
        self.assertEqual(len(estimated), 1)
        self.assertIn('data-coordinate-source="estimated"', estimated[0])
        self.assertIn('data-marker="D2S441" data-annotation="off-ladder-no-size"', svg)
        self.assertEqual(len(_peaks(svg, "D16S539")), 1)
        for marker, allele in (("TH01", "9.3"), ("D19S433", "14.2"), ("D1S1656", "15.3")):
            with self.subTest(marker=marker):
                self.assertTrue(any(f'data-allele="{allele}"' in p for p in _peaks(svg, marker)))

    def test_showcase_fixture_is_marked_as_synthetic(self) -> None:
        sample_names = {
            line.split("\t", 1)[0] for line in FIXTURE.read_text(encoding="utf-8").splitlines()[1:]
        }
        self.assertEqual(sample_names, {"NGM_SHOWCASE"})
        sources = " ".join((ROOT / "docs" / "SOURCES.md").read_text(encoding="utf-8").split())
        self.assertIn("ngm_showcase.tsv", sources)


class ShowcasePageTests(unittest.TestCase):
    def test_page_shows_the_figure_and_explains_each_case(self) -> None:
        page = PAGE.read_text(encoding="utf-8")
        self.assertRegex(page, r"!\[[^\]]+\]\(\.\./examples/ngm_showcase_example\.svg\)")
        text = " ".join(page.split())
        for phrase in ("D21S11", "D2S441", "vWA", "D16S539", "TH01", "synthetic"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_page_is_linked_from_the_entry_points(self) -> None:
        self.assertIn("](READING_THE_FIGURE.md)", (ROOT / "docs" / "index.md").read_text("utf-8"))
        guide = (ROOT / "docs" / "GETTING_STARTED.md").read_text(encoding="utf-8")
        self.assertIn("](READING_THE_FIGURE.md)", guide)
        self.assertIn(PAGE_URL + ")", (ROOT / "README.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
