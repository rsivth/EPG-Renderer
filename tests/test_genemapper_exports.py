"""End-to-end contracts for complete, fully synthetic GeneMapper table exports.

The two fixtures below contain no real samples, run identifiers, operator
initials, or laboratory data. They are entirely invented, generated from the
bundled kit definitions so that the structural edge cases these tests exist to
protect -- an unnamed trailing export column, a marker call that fills the
highest displayed allele column, and duplicate display names that must stay
separate source injections -- keep being exercised the same way a real,
oddly-shaped export would exercise them. See tools/_gen_synthetic_fixtures.py
for the generator.
"""

from __future__ import annotations

import hashlib
import unittest
from pathlib import Path

from epg_renderer import load_kit, load_project, match_kits, position_sample, render_svg
from epg_renderer.kit_workflow import Confidence

FIXTURES = Path(__file__).with_name("fixtures") / "genemapper_exports"
ESSPLEX = FIXTURES / "essplex_se_qs_mixed_export.txt"
NGM_SELECT = FIXTURES / "ngm_select_mixed_export.txt"


class GeneMapperExportTests(unittest.TestCase):
    """Keep complete configurable exports parseable and renderable across releases."""

    def test_fixtures_are_pinned_synthetic_exports(self) -> None:
        expected = {
            ESSPLEX: "594415bd6e6015a6fd62fd24b729e9da89a12322178a4d5cfde6cfc121639b20",
            NGM_SELECT: "4711b7dd24c6db92946b3f6f825bc3174a95f10cf92ec23ea00f358f0bb1d3cd",
        }
        for path, digest in expected.items():
            with self.subTest(path=path.name):
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)

    def test_essplex_se_qs_export_parses_without_losing_calls(self) -> None:
        project = load_project(ESSPLEX)
        self.assertEqual(len(project.samples), 7)
        self.assertEqual(sum(len(sample.markers) for sample in project.samples.values()), 133)
        self.assertEqual(
            sum(
                len(marker.alleles)
                for sample in project.samples.values()
                for marker in sample.markers.values()
            ),
            530,
        )
        self.assertEqual(
            max(
                len(marker.alleles)
                for sample in project.samples.values()
                for marker in sample.markers.values()
            ),
            20,
        )
        self.assertTrue(
            all(
                marker.dye is None
                for sample in project.samples.values()
                for marker in sample.markers.values()
            )
        )
        self.assertIn("empty unnamed trailing column", project.warnings[0])
        self.assertIn("Allele 20", project.warnings[1])

    def test_ngm_select_export_preserves_duplicate_display_names_as_injections(self) -> None:
        project = load_project(NGM_SELECT)
        self.assertEqual(len(project.samples), 31)
        self.assertEqual(sum(len(sample.markers) for sample in project.samples.values()), 527)
        self.assertEqual(
            sum(
                len(marker.alleles)
                for sample in project.samples.values()
                for marker in sample.markers.values()
            ),
            1497,
        )
        ladders = [
            sample for sample in project.samples.values() if sample.display_name == "Allelleiter"
        ]
        self.assertEqual(len(ladders), 2)
        self.assertEqual(
            {sample.sample_file for sample in ladders},
            {"A01_Ladder_01.hid", "H01_Ladder_08.hid"},
        )
        self.assertEqual(len({sample.sample_id for sample in ladders}), 2)
        self.assertEqual(len({sample.source_sample_id for sample in ladders}), 2)

    def test_complete_exports_identify_their_distinct_kits(self) -> None:
        cases = (
            (ESSPLEX, "Ess_Leiter", "Investigator ESSplex SE QS"),
            (NGM_SELECT, "Allelleiter-1", "NGM SElect"),
        )
        for path, sample_id, expected_kit in cases:
            with self.subTest(path=path.name):
                sample = load_project(path).sample(sample_id)
                match = match_kits(sample, genemapper_only=True)[0]
                self.assertEqual(match.kit.name, expected_kit)
                self.assertIs(match.confidence, Confidence.HIGH)
                self.assertEqual(match.marker_coverage, 1.0)
                self.assertEqual(match.order_agreement, 1.0)
                self.assertEqual(match.dye_observations, 0)

    def test_every_injection_positions_and_renders_with_its_kit(self) -> None:
        cases = (
            (ESSPLEX, "Investigator ESSplex SE QS"),
            (NGM_SELECT, "NGM SElect"),
        )
        for path, kit_name in cases:
            project = load_project(path)
            expected_peaks = sum(
                len(marker.alleles)
                for sample in project.samples.values()
                for marker in sample.markers.values()
            )
            rendered_peaks = 0
            for sample in project.samples.values():
                with self.subTest(path=path.name, sample=sample.sample_id):
                    positioned = position_sample(sample, kit_name=kit_name)
                    svg = render_svg(positioned)
                    self.assertIn(f'data-kit="{kit_name}"', svg)
                    rendered_peaks += svg.count('class="called-peak"')
            self.assertEqual(rendered_peaks, expected_peaks)

    def test_new_kit_profiles_expose_controls_and_se33_layout(self) -> None:
        essplex = load_kit("Investigator ESSplex SE QS")
        self.assertTrue(essplex.marker_metadata["QS1"].is_control)
        self.assertTrue(essplex.marker_metadata["QS2"].is_control)
        self.assertEqual(essplex.kit.marker("SE33").dye, "BTG")
        ngm_select = load_kit("NGM SElect")
        self.assertEqual(ngm_select.kit.marker("SE33").dye, "PET")
        self.assertNotIn("SE33", tuple(marker.name for marker in load_kit("NGM").kit.markers))


if __name__ == "__main__":
    unittest.main()
