from __future__ import annotations

import unittest
from collections import OrderedDict
from decimal import Decimal
from pathlib import Path

from epg_renderer import (
    load_kit,
    load_project,
    match_kits,
    position_sample,
)
from epg_renderer.kit_workflow import (
    Confidence,
    KitResolutionError,
    resolve_kit,
)
from epg_renderer.models import (
    MarkerCall,
    SampleCall,
)
from epg_renderer.positions import (
    CoordinateQualityError,
    DyeMismatchPositionError,
    PositionModelError,
)

FIXTURES = Path(__file__).with_name("fixtures")


class NgmDefinitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = load_kit("NGM")
        cls.kit = cls.profile.kit
        cls.model = cls.profile.coordinate_model

    def test_ngm_has_16_loci(self):
        self.assertEqual(len(self.kit.markers), 16)

    def test_ngm_has_four_sample_dye_channels(self):
        self.assertEqual(
            [channel.code for channel in self.kit.channels], ["FAM", "VIC", "NED", "PET"]
        )

    def test_ngm_marker_order_matches_manual(self):
        self.assertEqual(
            self.kit.source_marker_order,
            (
                "D10S1248",
                "vWA",
                "D16S539",
                "D2S1338",
                "Amelogenin",
                "D8S1179",
                "D21S11",
                "D18S51",
                "D22S1045",
                "D19S433",
                "TH01",
                "FGA",
                "D2S441",
                "D3S1358",
                "D1S1656",
                "D12S391",
            ),
        )

    def test_ngm_panel_ranges_match_manual_panel_table(self):
        expected = {
            "D10S1248": ("72.0", "127.0"),
            "vWA": ("149.0", "214.3"),
            "D16S539": ("223.6", "277.6"),
            "D2S1338": ("281.6", "356.0"),
            "Amelogenin": ("100.0", "108.0"),
            "D8S1179": ("117.9", "174.9"),
            "D21S11": ("178.8", "249.8"),
            "D18S51": ("259.5", "347.5"),
            "D22S1045": ("76.0", "120.0"),
            "D19S433": ("122.3", "166.3"),
            "TH01": ("176.4", "221.1"),
            "FGA": ("221.6", "372.0"),
            "D2S441": ("74.5", "113.4"),
            "D3S1358": ("114.4", "168.4"),
            "D1S1656": ("170.0", "224.0"),
            "D12S391": ("225.0", "287.0"),
        }
        for marker, bounds in expected.items():
            with self.subTest(marker=marker):
                definition = self.model.marker(marker)
                self.assertEqual(
                    (definition.range_min_bp, definition.range_max_bp),
                    tuple(Decimal(value) for value in bounds),
                )

    def test_every_ngm_ladder_allele_has_a_coordinate(self):
        for marker in self.kit.markers:
            with self.subTest(marker=marker.name):
                definition = self.model.marker(marker.name)
                self.assertEqual(
                    tuple(item.allele for item in definition.coordinates), marker.ladder_alleles
                )

    def test_ngm_d22s1045_is_trinucleotide(self):
        marker = self.model.marker("D22S1045")
        self.assertEqual(marker.repeat_length_bp, 3)
        self.assertEqual(marker.coordinate("9").nominal_bp - marker.coordinate("8").nominal_bp, 3)

    def test_ngm_microvariants_preserve_nucleotide_remainder(self):
        self.assertEqual(
            self.model.marker("TH01").coordinate("9.3").nominal_bp
            - self.model.marker("TH01").coordinate("9").nominal_bp,
            3,
        )
        self.assertEqual(
            self.model.marker("D21S11").coordinate("24.2").nominal_bp
            - self.model.marker("D21S11").coordinate("24").nominal_bp,
            2,
        )

    def test_amelogenin_alias_and_nominal_spacing(self):
        marker = self.model.marker("AM")
        self.assertEqual(marker.coordinate("X").nominal_bp, Decimal("101.0"))
        self.assertEqual(marker.coordinate("Y").nominal_bp, Decimal("107.0"))

    def test_ngm_definition_does_not_claim_exact_bins(self):
        self.assertFalse(self.model.exact_bin_centres)
        with self.assertRaises(CoordinateQualityError):
            self.model.require_exact()


class NgmDetectionAndPositioningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sample = load_project(FIXTURES / "ngm_minimal.tsv").sample("N1")

    def test_ngm_is_detected_exactly(self):
        best = match_kits(self.sample)[0]
        self.assertEqual(best.kit.name, "NGM")
        self.assertEqual(best.confidence, Confidence.EXACT)

    def test_globalfiler_is_not_a_plausible_exact_match_for_ngm(self):
        matches = {match.kit.name: match for match in match_kits(self.sample)}
        self.assertEqual(matches["GlobalFiler"].confidence, Confidence.NO_MATCH)
        self.assertLess(matches["GlobalFiler"].dye_agreement, 0.75)

    def test_explicit_ngm_alias_is_accepted(self):
        self.assertEqual(resolve_kit(self.sample, kit_name="AmpFlSTR NGM").kit.name, "NGM")

    def test_sparse_ngm_profile_can_be_selected_explicitly(self):
        sparse = SampleCall("N", OrderedDict(list(self.sample.markers.items())[:4]))
        match = resolve_kit(sparse, kit_name="NGM")
        self.assertEqual(match.kit.name, "NGM")
        self.assertEqual(match.confidence, Confidence.LOW)

    def test_sparse_ngm_profile_is_not_auto_accepted(self):
        sparse = SampleCall("N", OrderedDict(list(self.sample.markers.items())[:4]))
        with self.assertRaises(KitResolutionError):
            resolve_kit(sparse)

    def test_wrong_ngm_dye_is_rejected_for_explicit_kit(self):
        markers = dict(self.sample.markers)
        original = markers["D2S441"]
        markers["D2S441"] = MarkerCall(original.marker, "NED", original.alleles)
        modified = SampleCall(self.sample.sample_id, markers)
        with self.assertRaises(KitResolutionError):
            resolve_kit(modified, kit_name="NGM")

    def test_ngm_positioning_returns_only_called_peaks(self):
        positioned = position_sample(self.sample)
        self.assertEqual(positioned.kit_name, "NGM")
        self.assertEqual(positioned.coordinate_model_version, "0.4-ngm1")
        self.assertEqual(len(positioned.peaks), 32)
        self.assertEqual(len(positioned.issues), 0)

    def test_pet_calls_are_positioned_in_pet_channel(self):
        positioned = position_sample(self.sample)
        pet = [peak for peak in positioned.peaks if peak.dye == "PET"]
        self.assertEqual(len(pet), 8)
        self.assertTrue(
            all(peak.marker in {"D2S441", "D3S1358", "D1S1656", "D12S391"} for peak in pet)
        )

    def test_registered_positioning_permissive_mode_records_unknown_marker(self):
        markers = dict(self.sample.markers)
        markers["Unknown"] = MarkerCall("Unknown", "PET", ())
        modified = SampleCall(self.sample.sample_id, markers)
        positioned = position_sample(modified, kit_name="NGM", strict=False)
        self.assertEqual([issue.code for issue in positioned.issues], ["unknown_marker"])

    def test_registered_positioning_strict_mode_rejects_unknown_marker(self):
        markers = dict(self.sample.markers)
        markers["Unknown"] = MarkerCall("Unknown", "PET", ())
        modified = SampleCall(self.sample.sample_id, markers)
        with self.assertRaises(PositionModelError):
            position_sample(modified, kit_name="NGM", strict=True)

    def test_registered_positioning_permissive_mode_records_dye_mismatch(self):
        markers = dict(self.sample.markers)
        original = markers["D2S441"]
        markers["D2S441"] = MarkerCall(original.marker, "NED", original.alleles)
        modified = SampleCall(self.sample.sample_id, markers)
        positioned = position_sample(modified, kit_name="NGM", strict=False)
        self.assertIn("dye_mismatch", [issue.code for issue in positioned.issues])

    def test_registered_positioning_strict_mode_rejects_dye_mismatch(self):
        markers = dict(self.sample.markers)
        original = markers["D2S441"]
        markers["D2S441"] = MarkerCall(original.marker, "NED", original.alleles)
        modified = SampleCall(self.sample.sample_id, markers)
        with self.assertRaises(DyeMismatchPositionError):
            position_sample(modified, kit_name="NGM", strict=True)


if __name__ == "__main__":
    unittest.main()
