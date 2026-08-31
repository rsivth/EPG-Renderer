from __future__ import annotations

import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from epg_renderer.batch import BatchRenderItem, BatchRenderResult
from epg_renderer.domain import BatchStatus, PeakHeightMode, ProfileOrigin
from epg_renderer.manual_profile import ManualMarkerEntry, ManualProfile, ManualProfileError
from epg_renderer.positions import (
    CoordinateKind,
    PeakCoordinateSource,
    PositionedPeak,
    PositionedSample,
    PositioningIssue,
)
from epg_renderer.render_options import OutputFormat


def _peak(**changes: object) -> PositionedPeak:
    values: dict[str, object] = {
        "marker": "D3S1358",
        "dye": "FAM",
        "source_dye": "6-FAM",
        "allele_index": 1,
        "allele": "15",
        "height": 100,
        "coordinate_bp": Decimal("120"),
        "marker_range_min_bp": Decimal("100"),
        "marker_range_max_bp": Decimal("150"),
        "coordinate_source": PeakCoordinateSource.MEASURED,
        "annotation_only": False,
    }
    values.update(changes)
    return PositionedPeak(**values)  # type: ignore[arg-type]


def _sample(
    *, peaks: tuple[PositionedPeak, ...] | None = None, **changes: object
) -> PositionedSample:
    values: dict[str, object] = {
        "sample_id": "S1",
        "kit_name": "GlobalFiler",
        "coordinate_model_version": "0.2",
        "coordinate_kind": CoordinateKind.RANGE_CENTERED_NOMINAL,
        "exact_bin_centres": False,
        "peaks": (_peak(),) if peaks is None else peaks,
        "issues": (),
        "display_name": None,
        "origin": ProfileOrigin.GENEMAPPER,
        "height_mode": PeakHeightMode.RFU,
    }
    values.update(changes)
    return PositionedSample(**values)  # type: ignore[arg-type]


class PositionedValueInvariantTests(unittest.TestCase):
    def test_positioning_issue_normalizes_optional_text(self) -> None:
        issue = PositioningIssue(" missing_height ", " Missing height. ", " TPOX ", " 8 ")
        self.assertEqual(
            (issue.code, issue.message, issue.marker, issue.allele),
            ("missing_height", "Missing height.", "TPOX", "8"),
        )
        self.assertIsNone(PositioningIssue("code", "message", "TPOX", "  ").allele)

    def test_positioning_issue_rejects_blank_required_fields(self) -> None:
        for values in (("", "message", "TPOX"), ("code", "", "TPOX"), ("code", "message", "")):
            with self.subTest(values=values), self.assertRaises(ValueError):
                PositioningIssue(*values)

    def test_positioned_peak_normalizes_valid_scalar_values(self) -> None:
        peak = _peak(
            marker=" D3S1358 ",
            dye=" FAM ",
            source_dye="  ",
            allele=" 15 ",
            coordinate_bp="120.5",
            marker_range_min_bp="100",
            marker_range_max_bp="150",
        )
        self.assertEqual((peak.marker, peak.dye, peak.allele), ("D3S1358", "FAM", "15"))
        self.assertIsNone(peak.source_dye)
        self.assertEqual(peak.coordinate_bp, Decimal("120.5"))
        self.assertIsInstance(peak.marker_range_min_bp, Decimal)

    def test_positioned_peak_rejects_invalid_identity_and_height(self) -> None:
        invalid = (
            {"marker": ""},
            {"dye": ""},
            {"allele": ""},
            {"allele_index": 0},
            {"allele_index": True},
            {"height": -1},
            {"height": 32_768},
            {"height": True},
            {"annotation_only": 1},
            {"coordinate_source": "measured"},
        )
        for changes in invalid:
            with self.subTest(changes=changes), self.assertRaises((TypeError, ValueError)):
                _peak(**changes)

    def test_positioned_peak_rejects_invalid_coordinate_geometry(self) -> None:
        invalid = (
            {"coordinate_bp": "not-a-number"},
            {"coordinate_bp": Decimal("NaN")},
            {"marker_range_min_bp": Decimal("NaN")},
            {"marker_range_min_bp": Decimal("-1")},
            {"marker_range_min_bp": Decimal("150")},
            {"marker_range_max_bp": Decimal("100")},
            {"coordinate_bp": Decimal("99")},
            {"coordinate_bp": Decimal("151")},
        )
        for changes in invalid:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                _peak(**changes)

    def test_positioned_peak_rejects_coordinate_provenance_contradictions(self) -> None:
        invalid = (
            {"coordinate_bp": None, "coordinate_source": PeakCoordinateSource.MEASURED},
            {"coordinate_source": PeakCoordinateSource.UNPOSITIONED},
            {"annotation_only": True},
        )
        for changes in invalid:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                _peak(**changes)

        annotation = _peak(
            coordinate_bp=None,
            coordinate_source=PeakCoordinateSource.UNPOSITIONED,
            annotation_only=True,
        )
        self.assertTrue(annotation.annotation_only)

    def test_positioned_sample_normalizes_valid_values_and_sequences(self) -> None:
        peaks = [_peak()]
        issues = [PositioningIssue("code", "message", "D3S1358")]
        sample = _sample(
            sample_id=" S1 ",
            kit_name=" GlobalFiler ",
            coordinate_model_version=" 0.2 ",
            peaks=peaks,
            issues=issues,
            display_name=" Display ",
        )
        peaks.clear()
        issues.clear()
        self.assertEqual(sample.sample_id, "S1")
        self.assertEqual(sample.kit_name, "GlobalFiler")
        self.assertEqual(sample.coordinate_model_version, "0.2")
        self.assertEqual(sample.display_name, "Display")
        self.assertEqual(len(sample.peaks), 1)
        self.assertEqual(len(sample.issues), 1)

    def test_positioned_sample_rejects_invalid_structure(self) -> None:
        invalid = (
            {"sample_id": ""},
            {"kit_name": ""},
            {"coordinate_model_version": ""},
            {"exact_bin_centres": 1},
            {"peaks": (object(),)},
            {"issues": (object(),)},
            {"origin": "genemapper"},
            {"height_mode": "rfu"},
        )
        for changes in invalid:
            with self.subTest(changes=changes), self.assertRaises((TypeError, ValueError)):
                _sample(**changes)

    def test_positioned_sample_rejects_cross_field_contradictions(self) -> None:
        invalid = (
            {
                "coordinate_kind": CoordinateKind.EXACT_BIN_CENTRES,
                "exact_bin_centres": False,
            },
            {"exact_bin_centres": True},
            {"peaks": (_peak(height=None),)},
            {
                "peaks": (_peak(),),
                "height_mode": PeakHeightMode.UNIFORM,
            },
            {"peaks": (_peak(), replace(_peak(), allele="16"))},
        )
        for changes in invalid:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                _sample(**changes)

        uniform = _sample(peaks=(_peak(height=None),), height_mode=PeakHeightMode.UNIFORM)
        self.assertIs(uniform.height_mode, PeakHeightMode.UNIFORM)


class ManualValueInvariantTests(unittest.TestCase):
    def test_manual_marker_entry_enforces_height_contract(self) -> None:
        entry = ManualMarkerEntry(" D3S1358 ", [" 15 ", "16"], [1, 32_767])
        self.assertEqual(entry.marker, "D3S1358")
        self.assertEqual(entry.alleles, ("15", "16"))
        self.assertEqual(entry.heights, (1, 32_767))

        invalid = (
            (("15", "16"), (100,)),
            (("15",), (0,)),
            (("15",), (32_768,)),
            (("15",), (True,)),
        )
        for alleles, heights in invalid:
            with (
                self.subTest(alleles=alleles, heights=heights),
                self.assertRaises(ManualProfileError),
            ):
                ManualMarkerEntry("D3S1358", alleles, heights)

    def test_manual_profile_normalizes_and_validates_local_structure(self) -> None:
        entry = ManualMarkerEntry("D3S1358", ("15",), (100,))
        profile = ManualProfile(" Profile ", " GlobalFiler ", PeakHeightMode.RFU, [entry])
        self.assertEqual(profile.name, "Profile")
        self.assertEqual(profile.kit_name, "GlobalFiler")
        self.assertEqual(profile.markers, (entry,))

        invalid = (
            {"kit_name": ""},
            {"markers": ()},
            {"markers": (object(),)},
            {"markers": (entry, entry)},
            {
                "height_mode": PeakHeightMode.UNIFORM,
                "markers": (entry,),
            },
            {
                "height_mode": PeakHeightMode.RFU,
                "markers": (ManualMarkerEntry("D3S1358", ("15",), None),),
            },
        )
        defaults: dict[str, object] = {
            "name": "Profile",
            "kit_name": "GlobalFiler",
            "height_mode": PeakHeightMode.RFU,
            "markers": (entry,),
        }
        for changes in invalid:
            values = {**defaults, **changes}
            with self.subTest(changes=changes), self.assertRaises((TypeError, ManualProfileError)):
                ManualProfile(**values)  # type: ignore[arg-type]


class BatchValueInvariantTests(unittest.TestCase):
    def test_batch_item_requires_status_payload_coherence(self) -> None:
        succeeded = BatchRenderItem(" S1 ", "out/S1.svg", BatchStatus.SUCCEEDED)
        failed = BatchRenderItem(" S2 ", None, BatchStatus.FAILED, " failed ")
        self.assertEqual(succeeded.output_path, Path("out/S1.svg"))
        self.assertEqual(failed.error, "failed")

        invalid = (
            ("S", None, BatchStatus.SUCCEEDED, None),
            ("S", Path("out.svg"), BatchStatus.SUCCEEDED, "error"),
            ("S", Path("out.svg"), BatchStatus.FAILED, "error"),
            ("S", None, BatchStatus.FAILED, None),
            ("S", None, BatchStatus.FAILED, "   "),
        )
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(ValueError):
                BatchRenderItem(*values)

    def test_batch_result_rejects_invalid_item_collections(self) -> None:
        item = BatchRenderItem("S", "out/S.svg", BatchStatus.SUCCEEDED)
        result = BatchRenderResult(
            "input.tsv",
            "out",
            " GlobalFiler ",
            OutputFormat.SVG,
            [item],
            "out/manifest.json",
        )
        self.assertEqual(result.kit_name, "GlobalFiler")
        self.assertEqual(result.items, (item,))

        with self.assertRaises(TypeError):
            replace(result, items=(object(),))
        with self.assertRaises(ValueError):
            replace(result, items=(item, item))
        with self.assertRaises(ValueError):
            replace(result, kit_name="   ")


if __name__ == "__main__":
    unittest.main()
