"""Regressions for off-ladder calls in manual profiles.

Until 0.15.0.dev1 a manual profile could not contain an off-ladder call: "OL" was
rejected as an allele that cannot be positioned. Since 0.15.0.dev2 a manual entry
``OL@<allele>`` draws a peak labelled "OL" at the estimated position of the given
helper allele. The helper allele must not be a ladder allele of the marker, because a
peak in a ladder bin would be called as that allele and not as OL; its estimated
position must lie inside the marker range. GeneMapper exports cannot use this syntax.
"""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from epg_renderer import load_project, position_sample
from epg_renderer.domain import PeakHeightMode
from epg_renderer.manual_profile import (
    ManualMarkerEntry,
    ManualProfileError,
    build_manual_profile,
    parse_manual_marker_text,
)
from epg_renderer.models import AlleleCall
from epg_renderer.positions import PeakCoordinateSource, PositionModelError
from epg_renderer.render_document import render_positioned_sample_svg
from epg_renderer.render_options import SvgRenderError
from epg_renderer.workflow import render_manual_epg_report

ROOT = Path(__file__).resolve().parents[1]


def _profile(alleles: tuple[str, ...], *, marker: str = "D21S11", heights=None, kit="NGM"):
    mode = PeakHeightMode.UNIFORM if heights is None else PeakHeightMode.RFU
    return build_manual_profile(
        "Teaching",
        kit,
        {marker: ManualMarkerEntry(marker, alleles, heights)},
        height_mode=mode,
    )


class ManualOffLadderEntryTests(unittest.TestCase):
    def test_gui_row_text_keeps_the_off_ladder_token(self) -> None:
        entry = parse_manual_marker_text("D21S11", "30, 32.2; OL@34.1", "", "uniform")
        assert entry is not None
        self.assertEqual(entry.alleles, ("30", "32.2", "OL@34.1"))

    def test_off_ladder_call_carries_its_helper_allele(self) -> None:
        profile = _profile(("30", "ol@34.10"))
        self.assertEqual(profile.markers[0].alleles, ("30", "OL@34.1"))
        calls = profile.to_sample_call().markers["D21S11"].alleles
        self.assertEqual(
            [(c.allele, c.position_allele) for c in calls], [("30", None), ("OL", "34.1")]
        )

    def test_ladder_allele_as_helper_is_rejected_with_a_hint(self) -> None:
        with self.assertRaisesRegex(ManualProfileError, r"34 is a ladder allele.*OL@34\.1"):
            _profile(("OL@34",))

    def test_helper_allele_outside_the_marker_range_is_rejected(self) -> None:
        with self.assertRaisesRegex(ManualProfileError, "outside the D21S11 range"):
            _profile(("OL@50",))

    def test_invalid_off_ladder_entries_are_rejected(self) -> None:
        cases = (
            (("OL",), "OL@"),
            (("16@34.1",), "Only OL"),
            (("OL@",), "OL@"),
            (("OL@abc",), "cannot be positioned"),
        )
        for alleles, message in cases:
            with self.subTest(alleles=alleles), self.assertRaisesRegex(ManualProfileError, message):
                _profile(alleles)
        with self.assertRaisesRegex(ManualProfileError, "cannot be positioned"):
            _profile(("OL@Z",), marker="Amelogenin")

    def test_off_ladder_calls_need_distinct_helper_alleles(self) -> None:
        self.assertEqual(len(_profile(("OL@23", "OL@34.1")).markers[0].alleles), 2)
        with self.assertRaisesRegex(ManualProfileError, "duplicate allele"):
            _profile(("OL@34.1", "OL@34.10"))


class ManualOffLadderRenderTests(unittest.TestCase):
    def _render(self, profile):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "figure.svg"
            report = render_manual_epg_report(profile, output)
            return output.read_text(encoding="utf-8"), report

    def test_off_ladder_peak_is_drawn_at_the_estimated_helper_position(self) -> None:
        for heights in (None, (900, 600)):
            with self.subTest(heights=heights):
                svg, report = self._render(_profile(("30", "OL@34.1"), heights=heights))
                peak = re.search(r'<g class="called-peak"[^>]*data-allele="OL"[^>]*>', svg)
                assert peak is not None
                self.assertIn('data-coordinate-source="estimated"', peak[0])
                self.assertIn('data-coordinate-bp="227.3"', peak[0])
                self.assertIn('data-position-allele="34.1"', peak[0])
                self.assertIn('class="allele-label">OL<', svg)
                self.assertFalse(report.has_omitted_peaks)
                self.assertTrue(any("34.1" in message for message in report.messages()))

    def test_genemapper_samples_cannot_use_helper_alleles(self) -> None:
        sample = load_project(ROOT / "tests" / "fixtures" / "ngm_minimal.tsv").sample("N1")
        marker = sample.markers["D21S11"]
        forged = AlleleCall(allele_index=3, allele="OL", height=500, position_allele="34.1")
        object.__setattr__(marker, "alleles", (*marker.alleles, forged))
        with self.assertRaisesRegex(PositionModelError, "manual profiles"):
            position_sample(sample, kit_name="NGM")

    def test_renderer_rejects_a_helper_allele_without_an_estimated_coordinate(self) -> None:
        profile = _profile(("OL@34.1",))
        positioned = position_sample(profile.to_sample_call(), kit_name="NGM")
        forged = positioned.peaks[0]
        object.__setattr__(forged, "coordinate_source", PeakCoordinateSource.NOMINAL)
        object.__setattr__(positioned, "peaks", (forged,))
        with self.assertRaisesRegex(SvgRenderError, "estimated"):
            render_positioned_sample_svg(positioned)


class ManualOffLadderDocumentationTests(unittest.TestCase):
    def test_gui_guide_documents_the_syntax_and_its_rules(self) -> None:
        guide = (ROOT / "docs" / "GETTING_STARTED.md").read_text(encoding="utf-8")
        section = " ".join(
            guide.split("## Create a manual profile\n", 1)[1].split("\n## ")[0].split()
        )
        for phrase in ("OL@", "ladder allele", "marker range", "estimated"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, section)

    def test_figure_guide_and_coordinate_model_mention_manual_off_ladder_calls(self) -> None:
        for name in ("READING_THE_FIGURE.md", "COORDINATE_MODEL.md"):
            with self.subTest(page=name):
                self.assertIn("OL@", (ROOT / "docs" / name).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
