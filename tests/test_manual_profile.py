from __future__ import annotations

import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from epg_renderer import render_svg
from epg_renderer.domain import PeakHeightMode, ProfileOrigin
from epg_renderer.gui_workflow import suggested_manual_output_path
from epg_renderer.kit_registry import available_kit_profiles
from epg_renderer.manual_profile import (
    ManualMarkerEntry,
    ManualProfileError,
    build_manual_profile,
    editable_marker_names,
    parse_manual_marker_text,
)
from epg_renderer.render_options import SvgRenderError, SvgRenderOptions
from epg_renderer.workflow import render_manual_epg

NAMESPACE = {"svg": "http://www.w3.org/2000/svg"}


def _root(svg: str) -> ET.Element:
    return ET.fromstring(svg)


def _elements(root: ET.Element, class_name: str) -> list[ET.Element]:
    return [
        element for element in root.iter() if class_name in element.attrib.get("class", "").split()
    ]


class ManualProfileParsingTests(unittest.TestCase):
    def test_text_parser_accepts_multiple_separators_and_positive_rfu_values(self) -> None:
        entry = parse_manual_marker_text(
            "D3S1358",
            "15, 16;17 18",
            "100,200;300 400",
            PeakHeightMode.RFU,
        )
        self.assertEqual(entry.alleles, ("15", "16", "17", "18"))
        self.assertEqual(entry.heights, (100, 200, 300, 400))

    def test_empty_row_is_ignored(self) -> None:
        self.assertIsNone(parse_manual_marker_text("D3S1358", "", "", PeakHeightMode.UNIFORM))

    def test_rfu_mode_requires_one_positive_integer_per_allele(self) -> None:
        invalid = (("15,16", "100"), ("15", "1.5"), ("15", "0"), ("", "100"))
        for alleles, heights in invalid:
            with (
                self.subTest(alleles=alleles, heights=heights),
                self.assertRaises(ManualProfileError),
            ):
                parse_manual_marker_text("D3S1358", alleles, heights, PeakHeightMode.RFU)

    def test_uniform_mode_rejects_entered_rfu_values(self) -> None:
        with self.assertRaisesRegex(ManualProfileError, "remove RFU values"):
            parse_manual_marker_text("D3S1358", "15", "100", PeakHeightMode.UNIFORM)


class ManualProfileValidationTests(unittest.TestCase):
    def test_technical_controls_are_not_editable(self) -> None:
        self.assertNotIn("IQCS", editable_marker_names("NGM Detect"))
        self.assertNotIn("IQCL", editable_marker_names("NGM Detect"))
        self.assertNotIn("QIS", editable_marker_names("PowerPlex 35GY"))
        self.assertNotIn("QIL", editable_marker_names("PowerPlex 35GY"))

    def test_profile_requires_at_least_one_peak(self) -> None:
        with self.assertRaisesRegex(ManualProfileError, "at least one allele"):
            build_manual_profile("Empty", "GlobalFiler", {}, height_mode=PeakHeightMode.UNIFORM)

    def test_duplicate_canonical_alleles_are_rejected(self) -> None:
        with self.assertRaisesRegex(ManualProfileError, "duplicate allele"):
            build_manual_profile(
                "Duplicate",
                "GlobalFiler",
                {"D3S1358": ManualMarkerEntry("D3S1358", ("15", "15.0"), None)},
                height_mode=PeakHeightMode.UNIFORM,
            )

    def test_unpositionable_allele_is_rejected_at_entry_boundary(self) -> None:
        with self.assertRaisesRegex(ManualProfileError, "cannot be positioned"):
            build_manual_profile(
                "Invalid",
                "GlobalFiler",
                {"Amelogenin": ManualMarkerEntry("Amelogenin", ("Z",), None)},
                height_mode=PeakHeightMode.UNIFORM,
            )

    def test_technical_control_entry_is_rejected(self) -> None:
        with self.assertRaisesRegex(ManualProfileError, "technical-control"):
            build_manual_profile(
                "Invalid",
                "NGM Detect",
                {"IQCS": ManualMarkerEntry("IQCS", ("1",), None)},
                height_mode=PeakHeightMode.UNIFORM,
            )

    def test_rfu_profile_uses_shared_sample_model_with_explicit_origin(self) -> None:
        profile = build_manual_profile(
            "Figure 1",
            "GlobalFiler",
            {"D3S1358": ManualMarkerEntry("D3S1358", ("15", "16", "17"), (100, 250, 400))},
            height_mode=PeakHeightMode.RFU,
        )
        sample = profile.to_sample_call()
        self.assertIs(sample.origin, ProfileOrigin.MANUAL)
        self.assertIs(sample.height_mode, PeakHeightMode.RFU)
        self.assertEqual(
            tuple(call.height for call in sample.markers["D3S1358"].alleles),
            (100, 250, 400),
        )

    def test_uniform_profile_does_not_invent_rfu_values(self) -> None:
        profile = build_manual_profile(
            "Teaching",
            "GlobalFiler",
            {"D3S1358": ManualMarkerEntry("D3S1358", ("15", "16"), None)},
            height_mode=PeakHeightMode.UNIFORM,
        )
        sample = profile.to_sample_call()
        self.assertIs(sample.height_mode, PeakHeightMode.UNIFORM)
        self.assertEqual(
            tuple(call.height for call in sample.markers["D3S1358"].alleles),
            (None, None),
        )

    def test_every_bundled_kit_accepts_and_renders_a_minimal_manual_profile(self) -> None:
        for kit_profile in available_kit_profiles():
            marker = next(
                item
                for item in kit_profile.kit.markers
                if not kit_profile.marker_metadata[item.name].is_control
            )
            allele = marker.ladder_alleles[0]
            with self.subTest(kit=kit_profile.kit.name):
                profile = build_manual_profile(
                    "Minimal",
                    kit_profile.kit.name,
                    {marker.name: ManualMarkerEntry(marker.name, (allele,), None)},
                    height_mode=PeakHeightMode.UNIFORM,
                )
                svg = render_svg(profile.to_sample_call(), kit_name=profile.kit_name)
                self.assertEqual(len(_elements(_root(svg), "called-peak")), 1)


class ManualProfileRenderingTests(unittest.TestCase):
    def test_uniform_render_omits_all_rfu_semantics(self) -> None:
        profile = build_manual_profile(
            "Schematic example",
            "GlobalFiler",
            {
                "D3S1358": ManualMarkerEntry("D3S1358", ("15", "16"), None),
                "vWA": ManualMarkerEntry("vWA", ("17",), None),
            },
            height_mode=PeakHeightMode.UNIFORM,
        )
        root = _root(render_svg(profile.to_sample_call(), kit_name=profile.kit_name))
        self.assertEqual(root.attrib["data-profile-origin"], "manual")
        self.assertEqual(root.attrib["data-peak-height-mode"], "uniform")
        self.assertFalse(_elements(root, "rfu-label"))
        self.assertFalse(_elements(root, "height-label"))
        self.assertFalse(_elements(root, "horizontal-grid"))
        peaks = _elements(root, "called-peak")
        self.assertTrue(peaks)
        self.assertTrue(all("data-rfu" not in peak.attrib for peak in peaks))
        self.assertEqual(len({peak.attrib["data-y-px"] for peak in peaks}), 1)
        metadata = json.loads(root.find("svg:metadata", NAMESPACE).text)
        self.assertEqual(metadata["profile_origin"], "manual")
        self.assertEqual(metadata["peak_height_mode"], "uniform")
        self.assertIsNone(metadata["rfu_scale_mode"])
        text = " ".join(root.itertext())
        self.assertIn("uniform non-quantitative peak heights", text)
        self.assertIn("no RFU measurements are represented", text)

    def test_rfu_render_preserves_user_values_and_manual_origin(self) -> None:
        profile = build_manual_profile(
            "RFU example",
            "GlobalFiler",
            {"D3S1358": ManualMarkerEntry("D3S1358", ("15", "16"), (100, 400))},
            height_mode=PeakHeightMode.RFU,
        )
        root = _root(render_svg(profile.to_sample_call(), kit_name=profile.kit_name))
        peaks = _elements(root, "called-peak")
        self.assertEqual({peak.attrib["data-rfu"] for peak in peaks}, {"100", "400"})
        self.assertEqual(len({peak.attrib["data-y-px"] for peak in peaks}), 2)
        self.assertTrue(_elements(root, "rfu-label"))
        text = " ".join(root.itertext())
        self.assertIn("manually entered schematic profile", text)
        self.assertIn("no analytical source file is represented", text)

    def test_uniform_render_rejects_fixed_rfu_axis(self) -> None:
        profile = build_manual_profile(
            "Uniform",
            "GlobalFiler",
            {"D3S1358": ManualMarkerEntry("D3S1358", ("15",), None)},
            height_mode=PeakHeightMode.UNIFORM,
        )
        with self.assertRaisesRegex(SvgRenderError, "fixed_max_rfu"):
            render_svg(
                profile.to_sample_call(),
                kit_name=profile.kit_name,
                options=SvgRenderOptions(fixed_max_rfu=1000),
            )

    def test_manual_workflow_writes_valid_svg(self) -> None:
        profile = build_manual_profile(
            "Paper figure",
            "GlobalFiler",
            {"D3S1358": ManualMarkerEntry("D3S1358", ("15",), None)},
            height_mode=PeakHeightMode.UNIFORM,
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "manual.svg"
            result = render_manual_epg(profile, output)
            root = ET.parse(result).getroot()
        self.assertEqual(root.attrib["data-profile-origin"], "manual")

    def test_manual_output_suggestion_is_sanitized(self) -> None:
        path = suggested_manual_output_path("Figure 1 / teaching", "jpeg", directory="output")
        self.assertEqual(path, Path("output") / "Figure_1___teaching_epg.jpg")


if __name__ == "__main__":
    unittest.main()
