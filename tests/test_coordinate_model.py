from __future__ import annotations

import unittest
from decimal import Decimal

from epg_renderer import load_kit
from epg_renderer.positions import (
    CoordinateKind,
    CoordinateQualityError,
    PlacementMethod,
    PositionModelError,
    UnknownAllelePositionError,
    allele_length_code,
    canonicalize_allele_label,
)


class CoordinateModelTests(unittest.TestCase):
    def setUp(self):
        self.kit = load_kit("GlobalFiler").kit
        self.model = load_kit("GlobalFiler").coordinate_model

    def test_model_is_internally_valid(self):
        self.model.validate(self.kit)

    def test_model_has_all_24_markers_in_kit_order(self):
        self.assertEqual(
            tuple(marker.marker for marker in self.model.markers),
            tuple(marker.name for marker in self.kit.markers),
        )

    def test_model_is_explicitly_approximate(self):
        self.assertEqual(self.model.coordinate_kind, CoordinateKind.RANGE_CENTERED_NOMINAL)
        self.assertFalse(self.model.exact_bin_centres)

    def test_exact_coordinates_cannot_be_claimed(self):
        with self.assertRaises(CoordinateQualityError):
            self.model.require_exact()

    def test_sources_are_recorded(self):
        self.assertEqual(len(self.model.sources), 2)
        self.assertTrue(any("MAN0029969" in source.title for source in self.model.sources))
        self.assertTrue(
            any("PCR amplification kits" in source.title for source in self.model.sources)
        )

    def test_globalfiler_specific_fam_ranges(self):
        expected = {
            "D3S1358": (90, 147),
            "vWA": (151, 215),
            "D16S539": (221, 274),
            "CSF1PO": (277, 325),
            "TPOX": (332, 385),
        }
        for marker, bounds in expected.items():
            with self.subTest(marker=marker):
                definition = self.model.marker(marker)
                self.assertEqual(
                    (definition.range_min_bp, definition.range_max_bp),
                    tuple(Decimal(value) for value in bounds),
                )

    def test_globalfiler_specific_ned_ranges(self):
        expected = {
            "D2S441": (75, 114),
            "D19S433": (115, 174),
            "TH01": (174, 220),
            "FGA": (221, 380),
        }
        for marker, bounds in expected.items():
            with self.subTest(marker=marker):
                definition = self.model.marker(marker)
                self.assertEqual(
                    (definition.range_min_bp, definition.range_max_bp),
                    tuple(Decimal(value) for value in bounds),
                )

    def test_globalfiler_specific_sid_ranges(self):
        expected = {
            "D10S1248": (80, 132),
            "D1S1656": (154, 210),
            "D12S391": (211, 271),
            "D2S1338": (275, 356),
        }
        for marker, bounds in expected.items():
            with self.subTest(marker=marker):
                definition = self.model.marker(marker)
                self.assertEqual(
                    (definition.range_min_bp, definition.range_max_bp),
                    tuple(Decimal(value) for value in bounds),
                )

    def test_every_ladder_allele_has_one_coordinate(self):
        for kit_marker in self.kit.markers:
            with self.subTest(marker=kit_marker.name):
                definition = self.model.marker(kit_marker.name)
                self.assertEqual(
                    tuple(coordinate.allele for coordinate in definition.coordinates),
                    kit_marker.ladder_alleles,
                )
                self.assertEqual(len(definition.coordinates), len(set(definition.coordinates)))

    def test_every_coordinate_lies_within_its_marker_range(self):
        for definition in self.model.markers:
            for coordinate in definition.coordinates:
                with self.subTest(marker=definition.marker, allele=coordinate.allele):
                    self.assertGreaterEqual(coordinate.nominal_bp, definition.range_min_bp)
                    self.assertLessEqual(coordinate.nominal_bp, definition.range_max_bp)

    def test_coordinates_increase_with_ladder_order(self):
        for definition in self.model.markers:
            values = [coordinate.nominal_bp for coordinate in definition.coordinates]
            with self.subTest(marker=definition.marker):
                self.assertEqual(values, sorted(values))

    def test_tetranucleotide_spacing(self):
        d3 = self.model.marker("D3S1358")
        self.assertEqual(d3.coordinate("10").nominal_bp - d3.coordinate("9").nominal_bp, 4)

    def test_trinucleotide_spacing_at_d22s1045(self):
        d22 = self.model.marker("D22S1045")
        self.assertEqual(d22.repeat_length_bp, 3)
        self.assertEqual(d22.coordinate("9").nominal_bp - d22.coordinate("8").nominal_bp, 3)

    def test_microvariant_spacing_is_in_base_pairs(self):
        th01 = self.model.marker("TH01")
        self.assertEqual(th01.coordinate("9.3").nominal_bp - th01.coordinate("9").nominal_bp, 3)
        d21 = self.model.marker("D21S11")
        self.assertEqual(d21.coordinate("24.2").nominal_bp - d21.coordinate("24").nominal_bp, 2)

    def test_tpox_uses_globalfiler_relocated_anchor(self):
        tpox = self.model.marker("TPOX")
        self.assertEqual(tpox.placement_method, PlacementMethod.ANCHORED_REPEAT)
        self.assertEqual(tpox.coordinate("8").nominal_bp, Decimal("349"))
        self.assertEqual(tpox.coordinate("5").nominal_bp, Decimal("337"))
        self.assertEqual(tpox.coordinate("15").nominal_bp, Decimal("377"))

    def test_amelogenin_uses_explicit_manufacturer_sizes(self):
        amel = self.model.marker("AM")
        self.assertEqual(amel.placement_method, PlacementMethod.EXPLICIT)
        self.assertEqual(amel.coordinate("X").nominal_bp, Decimal("99"))
        self.assertEqual(amel.coordinate("Y").nominal_bp, Decimal("105"))

    def test_yindel_uses_explicit_positions(self):
        yindel = self.model.marker("Y indel")
        self.assertEqual(yindel.coordinate("1").nominal_bp, Decimal("81"))
        self.assertEqual(yindel.coordinate("2").nominal_bp, Decimal("86"))

    def test_marker_alias_is_resolved(self):
        self.assertIs(self.model.marker("AM"), self.model.marker("Amelogenin"))

    def test_unknown_marker_raises_key_error(self):
        with self.assertRaises(KeyError):
            self.model.marker("Unknown")

    def test_unknown_allele_is_not_interpolated_silently(self):
        with self.assertRaises(UnknownAllelePositionError):
            self.model.marker("TPOX").coordinate("16")

    def test_model_is_cached(self):
        self.assertIs(self.model, load_kit("GFI").coordinate_model)

    def test_numeric_allele_normalization(self):
        self.assertEqual(canonicalize_allele_label(" 09.30 "), "9.3")
        self.assertEqual(canonicalize_allele_label("8.0"), "8")
        self.assertEqual(canonicalize_allele_label("x"), "X")

    def test_non_numeric_label_is_preserved(self):
        self.assertEqual(canonicalize_allele_label("OL"), "OL")

    def test_relative_length_code_for_microvariant(self):
        self.assertEqual(allele_length_code("9.3", 4), Decimal("39"))
        self.assertEqual(allele_length_code("11.3", 4), Decimal("47"))

    def test_invalid_microvariant_remainder_is_rejected(self):
        with self.assertRaises(PositionModelError):
            allele_length_code("9.4", 4)


if __name__ == "__main__":
    unittest.main()
