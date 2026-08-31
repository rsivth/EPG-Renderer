from __future__ import annotations

import unittest
from collections import OrderedDict
from pathlib import Path
from unittest.mock import patch

from epg_renderer import (
    load_project,
    match_kits,
)
from epg_renderer.kit_workflow import Confidence, KitMatch, KitResolutionError, resolve_kit
from epg_renderer.models import MarkerCall, SampleCall

FIXTURES = Path(__file__).with_name("fixtures")


class KitDetectionTests(unittest.TestCase):
    def setUp(self):
        self.sample = load_project(FIXTURES / "globalfiler_minimal.tsv").sample("S1")

    def test_exact_globalfiler_detection(self):
        match = match_kits(self.sample)[0]
        self.assertEqual(match.kit.name, "GlobalFiler")
        self.assertEqual(match.confidence, Confidence.EXACT)
        self.assertEqual(match.marker_coverage, 1.0)
        self.assertEqual(match.dye_agreement, 1.0)
        self.assertEqual(match.order_agreement, 1.0)

    def test_automatic_resolution_accepts_exact_match(self):
        self.assertEqual(resolve_kit(self.sample).kit.name, "GlobalFiler")

    def test_explicit_resolution_accepts_alias(self):
        self.assertEqual(resolve_kit(self.sample, kit_name="GFI").kit.name, "GlobalFiler")

    def test_one_missing_marker_is_high_confidence(self):
        markers = dict(self.sample.markers)
        markers.pop("D2S1338")
        modified = SampleCall(self.sample.sample_id, markers)
        match = match_kits(modified)[0]
        self.assertEqual(match.confidence, Confidence.HIGH)
        self.assertEqual(match.missing_markers, ("D2S1338",))

    def test_shuffled_order_is_not_exact(self):
        modified = SampleCall(
            self.sample.sample_id, OrderedDict(reversed(list(self.sample.markers.items())))
        )
        match = match_kits(modified)[0]
        self.assertNotEqual(match.confidence, Confidence.EXACT)
        self.assertLess(match.order_agreement, 0.1)

    def test_wrong_dye_is_reported(self):
        markers = dict(self.sample.markers)
        original = markers["TPOX"]
        markers["TPOX"] = MarkerCall(original.marker, "VIC", original.alleles)
        modified = SampleCall(self.sample.sample_id, markers)
        match = match_kits(modified)[0]
        self.assertIn("TPOX", match.dye_mismatches)
        self.assertLess(match.dye_agreement, 1.0)

    def test_unknown_marker_prevents_exact_match(self):
        markers = dict(self.sample.markers)
        markers["IQCS"] = MarkerCall("IQCS", "FAM", ())
        modified = SampleCall(self.sample.sample_id, markers)
        match = match_kits(modified)[0]
        self.assertEqual(match.unknown_markers, ("IQCS",))
        self.assertNotEqual(match.confidence, Confidence.EXACT)

    def test_sparse_profile_requires_explicit_kit(self):
        markers = OrderedDict(list(self.sample.markers.items())[:5])
        sparse = SampleCall("S", markers)
        with self.assertRaises(KitResolutionError):
            resolve_kit(sparse)

    def test_sparse_profile_can_use_explicit_kit_when_not_incompatible(self):
        markers = OrderedDict(list(self.sample.markers.items())[:5])
        sparse = SampleCall("S", markers)
        match = resolve_kit(sparse, kit_name="GlobalFiler")
        self.assertEqual(match.kit.name, "GlobalFiler")
        self.assertEqual(match.confidence, Confidence.LOW)

    def test_automatic_resolution_reports_empty_registry(self):
        with (
            patch("epg_renderer.kit_workflow.detect_kits", return_value=()),
            self.assertRaisesRegex(KitResolutionError, "No GeneMapper-compatible"),
        ):
            resolve_kit(self.sample, require_genemapper_compatible=True)

    def test_automatic_resolution_rejects_equal_top_scores(self):
        best = resolve_kit(self.sample, kit_name="GlobalFiler")
        tied = KitMatch(
            best.kit,
            best.confidence,
            best.marker_coverage,
            best.dye_agreement,
            best.order_agreement,
            best.missing_markers,
            best.unknown_markers,
            best.dye_mismatches,
            best.dye_observations,
        )
        with (
            patch("epg_renderer.kit_workflow.detect_kits", return_value=(best, tied)),
            self.assertRaisesRegex(KitResolutionError, "ambiguous"),
        ):
            resolve_kit(self.sample)

    def test_incompatible_explicit_kit_is_rejected(self):
        incompatible = SampleCall("S", OrderedDict({"Unknown": MarkerCall("Unknown", "FAM", ())}))
        with self.assertRaises(KitResolutionError):
            resolve_kit(incompatible, kit_name="GlobalFiler")
