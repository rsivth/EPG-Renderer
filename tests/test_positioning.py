from __future__ import annotations

import unittest
from collections import OrderedDict
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from pathlib import Path

from epg_renderer import (
    load_kit,
    load_project,
    position_sample,
)
from epg_renderer.models import (
    AlleleCall,
    MarkerCall,
    SampleCall,
)
from epg_renderer.positions import (
    AlleleCoordinate,
    CoordinateQualityError,
    DyeMismatchPositionError,
    MarkerCoordinateDefinition,
    PlacementMethod,
    PositionedSample,
    PositionModelError,
    UnknownAllelePositionError,
    allele_length_code,
    canonicalize_allele_label,
)

FIXTURES = Path(__file__).with_name("fixtures")


class SamplePositioningTests(unittest.TestCase):
    def setUp(self):
        self.project = load_project(FIXTURES / "globalfiler_minimal.tsv")
        self.sample = self.project.sample("S1")

    def test_positions_all_and_only_called_peaks(self):
        expected_calls = sum(len(marker.alleles) for marker in self.sample.markers.values())
        positioned = position_sample(self.sample)
        self.assertEqual(len(positioned.peaks), expected_calls)
        self.assertEqual(len(positioned.peaks), 43)

    def test_does_not_synthesize_stutter_or_artefacts(self):
        positioned = position_sample(self.sample)
        calls = {
            (
                "Amelogenin" if marker.marker == "AM" else marker.marker,
                allele.allele_index,
                allele.allele,
                allele.height,
            )
            for marker in self.sample.markers.values()
            for allele in marker.alleles
        }
        peaks = {
            (peak.marker, peak.allele_index, peak.allele, peak.height) for peak in positioned.peaks
        }
        self.assertEqual(peaks, calls)

    def test_automatic_kit_resolution(self):
        positioned = position_sample(self.sample)
        self.assertEqual(positioned.kit_name, "GlobalFiler")

    def test_explicit_kit_resolution(self):
        positioned = position_sample(self.sample, kit_name="GFI")
        self.assertEqual(positioned.kit_name, "GlobalFiler")

    def test_sparse_sample_can_be_positioned_with_explicit_kit(self):
        sparse = SampleCall("S", OrderedDict(list(self.sample.markers.items())[:2]))
        positioned = position_sample(sparse, kit_name="GlobalFiler")
        self.assertEqual(len(positioned.peaks), 4)

    def test_sparse_sample_without_explicit_kit_is_rejected(self):
        sparse = SampleCall("S", OrderedDict(list(self.sample.markers.items())[:2]))
        with self.assertRaises(ValueError):
            position_sample(sparse)

    def test_peak_heights_are_preserved(self):
        positioned = position_sample(self.sample)
        peak = next(p for p in positioned.peaks if p.marker == "D3S1358" and p.allele == "15")
        self.assertEqual(peak.height, 1200)

    def test_marker_alias_is_canonicalized(self):
        positioned = position_sample(self.sample)
        self.assertIn("Amelogenin", {peak.marker for peak in positioned.peaks})
        self.assertNotIn("AM", {peak.marker for peak in positioned.peaks})

    def test_peaks_are_sorted_by_channel_and_marker(self):
        positioned = position_sample(self.sample)
        marker_sequence = []
        for peak in positioned.peaks:
            if not marker_sequence or marker_sequence[-1] != peak.marker:
                marker_sequence.append(peak.marker)
        self.assertEqual(
            tuple(marker_sequence),
            (
                "D3S1358",
                "vWA",
                "D16S539",
                "CSF1PO",
                "TPOX",
                "Yindel",
                "Amelogenin",
                "D8S1179",
                "D21S11",
                "D18S51",
                "DYS391",
                "D2S441",
                "D19S433",
                "TH01",
                "FGA",
                "D22S1045",
                "D5S818",
                "D13S317",
                "D7S820",
                "SE33",
                "D10S1248",
                "D1S1656",
                "D12S391",
                "D2S1338",
            ),
        )

    def test_alleles_are_sorted_by_nominal_bp_within_marker(self):
        positioned = position_sample(self.sample)
        d3 = [peak for peak in positioned.peaks if peak.marker == "D3S1358"]
        self.assertEqual([peak.allele for peak in d3], ["15", "16"])
        self.assertLess(d3[0].coordinate_bp, d3[1].coordinate_bp)

    def test_tpox_call_uses_anchored_coordinate(self):
        positioned = position_sample(self.sample)
        tpox = next(peak for peak in positioned.peaks if peak.marker == "TPOX")
        self.assertEqual(tpox.coordinate_bp, Decimal("349"))

    def test_output_records_coordinate_quality(self):
        positioned = position_sample(self.sample)
        self.assertFalse(positioned.exact_bin_centres)
        self.assertEqual(positioned.coordinate_model_version, "0.2")

    def test_exact_bin_requirement_is_rejected(self):
        with self.assertRaises(CoordinateQualityError):
            position_sample(self.sample, require_exact_bin_centres=True)

    def test_numeric_off_ladder_allele_uses_repeat_based_estimate(self):
        marker = self.sample.markers["TPOX"]
        modified = SampleCall(
            "S", OrderedDict({"TPOX": MarkerCall("TPOX", marker.dye, (AlleleCall(1, "16", 100),))})
        )
        positioned = position_sample(modified, kit_name="GlobalFiler")
        self.assertEqual(positioned.peaks[0].coordinate_bp, Decimal("381"))
        self.assertEqual(positioned.issues[0].code, "estimated_allele_coordinate")

    def test_non_numeric_unknown_allele_is_rejected_in_strict_mode(self):
        marker = self.sample.markers["TPOX"]
        modified = SampleCall(
            "S", OrderedDict({"TPOX": MarkerCall("TPOX", marker.dye, (AlleleCall(1, "foo", 100),))})
        )
        with self.assertRaises(UnknownAllelePositionError):
            position_sample(modified, kit_name="GlobalFiler")

    def test_non_numeric_unknown_allele_is_recorded_in_permissive_mode(self):
        marker = self.sample.markers["TPOX"]
        modified = SampleCall(
            "S", OrderedDict({"TPOX": MarkerCall("TPOX", marker.dye, (AlleleCall(1, "foo", 100),))})
        )
        positioned = position_sample(modified, kit_name="GlobalFiler", strict=False)
        self.assertIsNone(positioned.peaks[0].coordinate_bp)
        self.assertEqual(positioned.issues[0].code, "unknown_allele")
        self.assertFalse(positioned.peaks[0].annotation_only)

    def test_off_ladder_without_size_is_preserved_as_marker_annotation(self):
        marker = self.sample.markers["TPOX"]
        modified = SampleCall(
            "S", OrderedDict({"TPOX": MarkerCall("TPOX", marker.dye, (AlleleCall(1, "OL", 100),))})
        )
        positioned = position_sample(modified, kit_name="GlobalFiler")
        self.assertIsNone(positioned.peaks[0].coordinate_bp)
        self.assertTrue(positioned.peaks[0].annotation_only)
        self.assertEqual(positioned.issues[0].code, "off_ladder_without_size")

    def test_dye_mismatch_is_rejected_in_strict_mode(self):
        marker = self.sample.markers["TPOX"]
        modified = SampleCall("S", OrderedDict({"TPOX": MarkerCall("TPOX", "VIC", marker.alleles)}))
        with self.assertRaises(DyeMismatchPositionError):
            position_sample(modified, kit_name="GlobalFiler")

    def test_dye_mismatch_is_recorded_in_permissive_mode(self):
        marker = self.sample.markers["TPOX"]
        modified = SampleCall("S", OrderedDict({"TPOX": MarkerCall("TPOX", "VIC", marker.alleles)}))
        positioned = position_sample(modified, kit_name="GlobalFiler", strict=False)
        self.assertEqual(positioned.peaks[0].dye, "FAM")
        self.assertEqual(positioned.peaks[0].source_dye, "VIC")
        self.assertEqual(positioned.issues[0].code, "dye_mismatch")

    def test_unknown_supplied_dye_is_rejected_in_strict_mode(self):
        marker = self.sample.markers["TPOX"]
        modified = SampleCall(
            "S",
            OrderedDict({"TPOX": MarkerCall("TPOX", "NOT-A-DYE", marker.alleles)}),
        )
        with self.assertRaisesRegex(DyeMismatchPositionError, "unrecognized dye"):
            position_sample(modified, kit_name="GlobalFiler")

    def test_unknown_supplied_dye_is_recorded_in_permissive_mode(self):
        marker = self.sample.markers["TPOX"]
        modified = SampleCall(
            "S",
            OrderedDict({"TPOX": MarkerCall("TPOX", "NOT-A-DYE", marker.alleles)}),
        )
        positioned = position_sample(modified, kit_name="GlobalFiler", strict=False)
        self.assertEqual(positioned.peaks[0].dye, "FAM")
        self.assertEqual(positioned.peaks[0].source_dye, "NOT-A-DYE")
        self.assertEqual(positioned.issues[0].code, "unknown_dye")
        self.assertEqual(positioned.issues[0].marker, "TPOX")

    def test_missing_source_dye_remains_valid(self):
        marker = self.sample.markers["TPOX"]
        modified = SampleCall("S", OrderedDict({"TPOX": MarkerCall("TPOX", None, marker.alleles)}))
        positioned = position_sample(modified, kit_name="GlobalFiler")
        self.assertIsNone(positioned.peaks[0].source_dye)
        self.assertEqual(positioned.issues, ())

    def test_source_dye_alias_remains_valid(self):
        marker = self.sample.markers["TPOX"]
        modified = SampleCall(
            "S", OrderedDict({"TPOX": MarkerCall("TPOX", "blue", marker.alleles)})
        )
        positioned = position_sample(modified, kit_name="GlobalFiler")
        self.assertEqual(positioned.peaks[0].dye, "FAM")
        self.assertEqual(positioned.peaks[0].source_dye, "blue")
        self.assertEqual(positioned.issues, ())

    def test_unknown_marker_is_rejected_in_strict_mode(self):
        modified = SampleCall(
            "S", OrderedDict({"Unknown": MarkerCall("Unknown", "FAM", (AlleleCall(1, "1", 100),))})
        )
        with self.assertRaises(PositionModelError):
            position_sample(modified, kit_name="GlobalFiler")

    def test_unknown_marker_is_skipped_in_permissive_mode(self):
        modified = SampleCall(
            "S", OrderedDict({"Unknown": MarkerCall("Unknown", "FAM", (AlleleCall(1, "1", 100),))})
        )
        positioned = position_sample(modified, kit_name="GlobalFiler", strict=False)
        self.assertEqual(positioned.peaks, ())
        self.assertEqual(positioned.issues[0].code, "unknown_marker")

    def test_mismatched_coordinate_model_is_rejected(self):
        model = replace(load_kit("GlobalFiler").coordinate_model, kit=load_kit("NGM").kit)
        with self.assertRaises(PositionModelError):
            position_sample(self.sample, coordinate_model=model)

    def test_missing_height_is_rejected_or_recorded(self):
        marker = MarkerCall("TPOX", "FAM", (AlleleCall(1, "8", None),))
        modified = SampleCall("S", OrderedDict({"TPOX": marker}))
        with self.assertRaisesRegex(PositionModelError, "no exported height"):
            position_sample(modified, kit_name="GlobalFiler")
        positioned = position_sample(modified, kit_name="GlobalFiler", strict=False)
        self.assertEqual(positioned.peaks, ())
        self.assertEqual(positioned.issues[0].code, "missing_height")

    def test_exported_size_overrides_kit_coordinate(self):
        marker = MarkerCall(
            "TPOX",
            None,
            (AlleleCall(1, "OL", 100, size_bp=Decimal("350.25")),),
        )
        modified = SampleCall("S", OrderedDict({"TPOX": marker}))
        positioned = position_sample(modified, kit_name="GlobalFiler")
        self.assertEqual(positioned.peaks[0].coordinate_bp, Decimal("350.25"))
        self.assertEqual(positioned.peaks[0].allele, "OL")
        self.assertEqual(positioned.issues, ())

    def test_position_value_objects_validate_enum_types(self):
        coordinate = AlleleCoordinate("1", Decimal("100"))
        with self.assertRaises(TypeError):
            MarkerCoordinateDefinition(
                "TPOX",
                "FAM",
                Decimal("90"),
                Decimal("110"),
                4,
                "repeat",
                (coordinate,),
                "test",
            )
        with self.assertRaises(TypeError):
            replace(load_kit("GlobalFiler").coordinate_model, coordinate_kind="nominal")
        with self.assertRaises(TypeError):
            PositionedSample("S", "GlobalFiler", "1", "nominal", False, (), ())

    def test_explicit_marker_does_not_estimate_unknown_allele(self):
        marker = MarkerCoordinateDefinition(
            "Amelogenin",
            "VIC",
            Decimal("100"),
            Decimal("120"),
            None,
            PlacementMethod.EXPLICIT,
            (AlleleCoordinate("X", Decimal("105")),),
            "test",
        )
        with self.assertRaises(UnknownAllelePositionError):
            marker.coordinate_or_estimate("Y")

    def test_estimate_outside_marker_range_is_rejected(self):
        marker = MarkerCoordinateDefinition(
            "TPOX",
            "FAM",
            Decimal("100"),
            Decimal("110"),
            4,
            PlacementMethod.ANCHORED_REPEAT,
            (AlleleCoordinate("8", Decimal("100")),),
            "test",
        )
        with self.assertRaisesRegex(UnknownAllelePositionError, "outside"):
            marker.coordinate_or_estimate("20")

    def test_empty_and_special_allele_labels_are_handled_explicitly(self):
        with self.assertRaises(UnknownAllelePositionError):
            canonicalize_allele_label(" ")
        self.assertEqual(canonicalize_allele_label("NaN"), "NaN")
        self.assertEqual(canonicalize_allele_label("-1"), "-1")
        with self.assertRaises(PositionModelError):
            allele_length_code("8", 0)

    def test_positioned_objects_are_immutable(self):
        positioned = position_sample(self.sample)
        with self.assertRaises(FrozenInstanceError):
            positioned.peaks[0].height = 1


if __name__ == "__main__":
    unittest.main()
