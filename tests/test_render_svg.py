from __future__ import annotations

import json
import math
import unittest
import xml.etree.ElementTree as ET
from collections import OrderedDict
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from unittest import mock

from epg_renderer import (
    load_project,
    position_sample,
    render_svg,
)
from epg_renderer.models import (
    AlleleCall,
    MarkerCall,
    SampleCall,
)
from epg_renderer.positions import PositionedPeak
from epg_renderer.render_metrics import _minimum_channel_height
from epg_renderer.render_options import (
    RfuScaleMode,
    SvgRenderError,
    SvgRenderOptions,
    UnpositionedPeakRenderError,
    UnpositionedPolicy,
)

FIXTURES = Path(__file__).with_name("fixtures")
NS = {"svg": "http://www.w3.org/2000/svg"}


def _root(svg: str) -> ET.Element:
    return ET.fromstring(svg)


def _elements(root: ET.Element, class_name: str) -> list[ET.Element]:
    return [
        element for element in root.iter() if class_name in element.attrib.get("class", "").split()
    ]


class SvgRendererStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        project = load_project(FIXTURES / "globalfiler_minimal.tsv")
        cls.sample = project.sample("S1")
        cls.positioned = position_sample(cls.sample)
        cls.svg = render_svg(cls.positioned)
        cls.root = _root(cls.svg)

    def test_output_is_complete_well_formed_utf8_svg(self):
        self.assertTrue(self.svg.startswith('<?xml version="1.0" encoding="UTF-8"?>'))
        self.assertEqual(self.root.tag, "{http://www.w3.org/2000/svg}svg")

    def test_default_dimensions_are_explicit(self):
        self.assertEqual(self.root.attrib["width"], "1600")
        self.assertEqual(self.root.attrib["height"], "1382")
        self.assertEqual(self.root.attrib["viewBox"], "0 0 1600 1382")

    def test_all_five_channels_are_rendered_in_kit_order(self):
        channels = _elements(self.root, "channel-panel")
        self.assertEqual(
            [element.attrib["data-dye"] for element in channels],
            ["FAM", "VIC", "NED", "TAZ", "SID"],
        )

    def test_all_24_marker_bands_are_rendered(self):
        bands = _elements(self.root, "marker-band")
        self.assertEqual(len(bands), 24)
        self.assertEqual(len({band.attrib["data-marker"] for band in bands}), 24)

    def test_all_and_only_called_peaks_are_rendered(self):
        rendered = {
            (
                element.attrib["data-marker"],
                element.attrib["data-allele"],
                int(element.attrib["data-rfu"]),
            )
            for element in _elements(self.root, "called-peak")
        }
        expected = {
            ("Amelogenin" if marker.marker == "AM" else marker.marker, allele.allele, allele.height)
            for marker in self.sample.markers.values()
            for allele in marker.alleles
        }
        self.assertEqual(rendered, expected)
        self.assertEqual(len(rendered), 43)

    def test_peak_metadata_include_nominal_bp_and_source_dye(self):
        peak = next(
            item
            for item in _elements(self.root, "called-peak")
            if item.attrib["data-marker"] == "TH01" and item.attrib["data-allele"] == "9.3"
        )
        self.assertEqual(peak.attrib["data-dye"], "NED")
        self.assertEqual(peak.attrib["data-source-dye"], "NED")
        self.assertTrue(Decimal(peak.attrib["data-nominal-bp"]).is_finite())

    def test_document_records_coordinate_quality_limitation(self):
        self.assertEqual(self.root.attrib["data-exact-bin-centres"], "false")
        description = self.root.find("svg:desc", NS)
        self.assertIsNotNone(description)
        self.assertIn("not measured fragment sizes", description.text)
        self.assertIn("or asserted exact GeneMapper bin centres", self.svg)

    def test_svg_has_no_raster_script_or_external_reference(self):
        forbidden = {"image", "script", "foreignObject", "use"}
        local_names = {element.tag.rpartition("}")[2] for element in self.root.iter()}
        self.assertTrue(forbidden.isdisjoint(local_names))
        self.assertNotIn("data:image", self.svg)
        self.assertNotIn("http://", self.svg.replace("http://www.w3.org/2000/svg", ""))
        self.assertNotIn("https://", self.svg)

    def test_output_is_deterministic(self):
        self.assertEqual(self.svg, render_svg(self.positioned))

    def test_special_characters_are_xml_safe(self):
        sample = SampleCall(
            "S<&\"'", OrderedDict({"TPOX": MarkerCall("TPOX", "FAM", (AlleleCall(1, "8", 500),))})
        )
        svg = render_svg(sample, kit_name="GlobalFiler")
        parsed = _root(svg)
        title = parsed.find("svg:title", NS)
        self.assertIn("S<&\"'", title.text)
        self.assertIn("&lt;", svg)
        self.assertIn("&amp;", svg)

    def test_channel_colors_follow_globalfiler_dye_conventions(self):
        expected = {
            "FAM": "#0067C5",
            "VIC": "#008B45",
            "NED": "#A87800",
            "TAZ": "#C62828",
            "SID": "#7B1FA2",
        }
        for channel in _elements(self.root, "channel-panel"):
            path = next(element for element in channel.iter() if element.tag.endswith("path"))
            self.assertEqual(path.attrib["stroke"], expected[channel.attrib["data-dye"]])

    def test_default_label_allocator_avoids_collisions_for_fixture(self):
        collisions = [
            item
            for item in _elements(self.root, "called-peak")
            if item.attrib["data-label-collision"] == "true"
        ]
        self.assertEqual(collisions, [])

    def test_label_lanes_are_bounded(self):
        lanes = {
            int(item.attrib["data-label-lane"]) for item in _elements(self.root, "called-peak")
        }
        self.assertTrue(lanes.issubset({0, 1, 2, 3}))

    def test_peak_x_order_follows_nominal_allele_order(self):
        d3 = [
            item
            for item in _elements(self.root, "called-peak")
            if item.attrib["data-marker"] == "D3S1358"
        ]
        by_allele = {item.attrib["data-allele"]: float(item.attrib["data-x-px"]) for item in d3}
        self.assertLess(by_allele["15"], by_allele["16"])

    def test_higher_rfu_peak_is_drawn_higher_within_same_channel(self):
        d3 = [
            item
            for item in _elements(self.root, "called-peak")
            if item.attrib["data-marker"] == "D3S1358"
        ]
        by_allele = {item.attrib["data-allele"]: float(item.attrib["data-y-px"]) for item in d3}
        self.assertLess(by_allele["15"], by_allele["16"])

    def test_global_rfu_scaling_uses_one_axis_maximum(self):
        svg = render_svg(
            self.positioned, options=SvgRenderOptions(rfu_scale_mode=RfuScaleMode.GLOBAL)
        )
        maxima = {
            int(item.attrib["data-rfu-max"]) for item in _elements(_root(svg), "channel-panel")
        }
        self.assertEqual(maxima, {1500})

    def test_fixed_rfu_scaling_uses_requested_maximum(self):
        svg = render_svg(self.positioned, options=SvgRenderOptions(fixed_max_rfu=2000))
        maxima = {
            int(item.attrib["data-rfu-max"]) for item in _elements(_root(svg), "channel-panel")
        }
        self.assertEqual(maxima, {2000})

    def test_fixed_rfu_maximum_cannot_clip_peak(self):
        with self.assertRaises(SvgRenderError):
            render_svg(self.positioned, options=SvgRenderOptions(fixed_max_rfu=1199))

    def test_sparse_sample_still_renders_all_kit_channels_and_markers(self):
        sparse = SampleCall(
            "S", OrderedDict({"TPOX": MarkerCall("TPOX", "FAM", (AlleleCall(1, "8", 500),))})
        )
        root = _root(render_svg(sparse, kit_name="GlobalFiler"))
        self.assertEqual(len(_elements(root, "channel-panel")), 5)
        self.assertEqual(len(_elements(root, "marker-band")), 24)
        self.assertEqual(len(_elements(root, "called-peak")), 1)
        self.assertEqual(len(_elements(root, "empty-channel")), 4)

    def test_unpositioned_peak_is_rejected_by_default(self):
        marker = self.sample.markers["TPOX"]
        sample = SampleCall(
            "S", OrderedDict({"TPOX": MarkerCall("TPOX", marker.dye, (AlleleCall(1, "foo", 100),))})
        )
        positioned = position_sample(sample, kit_name="GlobalFiler", strict=False)
        with self.assertRaises(UnpositionedPeakRenderError):
            render_svg(positioned)

    def test_unpositioned_peak_can_be_omitted_explicitly(self):
        sample = SampleCall(
            "S", OrderedDict({"TPOX": MarkerCall("TPOX", "FAM", (AlleleCall(1, "foo", 100),))})
        )
        positioned = position_sample(sample, kit_name="GlobalFiler", strict=False)
        svg = render_svg(
            positioned, options=SvgRenderOptions(unpositioned_policy=UnpositionedPolicy.OMIT)
        )
        root = _root(svg)
        self.assertEqual(len(_elements(root, "called-peak")), 0)
        metadata = json.loads(root.find("svg:metadata", NS).text)
        self.assertEqual(metadata["omitted_unpositioned_peaks"], 1)
        warning = _elements(root, "warning")
        self.assertEqual(len(warning), 1)
        self.assertEqual(warning[0].attrib["data-omitted-unpositioned-peaks"], "1")

    def test_off_ladder_without_size_renders_marker_ribbon_and_legend_instead_of_failing(self):
        sample = SampleCall(
            "S", OrderedDict({"TPOX": MarkerCall("TPOX", "FAM", (AlleleCall(1, "OL", 100),))})
        )
        root = _root(render_svg(sample, kit_name="GlobalFiler"))
        self.assertEqual(len(_elements(root, "called-peak")), 0)
        metadata = json.loads(root.find("svg:metadata", NS).text)
        self.assertEqual(metadata["omitted_unpositioned_peaks"], 0)
        self.assertEqual(metadata["marker_annotations"], {"TPOX": 1})
        self.assertEqual(
            metadata["marker_annotation_messages"],
            ["Marker TPOX contains unpositioned off-ladder allele(s) without size information."],
        )
        ribbons = _elements(root, "marker-annotation-ribbon")
        self.assertEqual(len(ribbons), 1)
        self.assertEqual(ribbons[0].attrib["data-marker"], "TPOX")
        self.assertEqual(ribbons[0].attrib["data-count"], "1")
        ribbon_text = ribbons[0].find("svg:text", NS)
        self.assertEqual(ribbon_text.text, "OL")
        self.assertEqual(ribbon_text.attrib["fill"], "#FFFFFF")
        self.assertEqual(ribbon_text.attrib["dominant-baseline"], "middle")
        polygon = ribbons[0].find("svg:polygon", NS)
        self.assertEqual(polygon.attrib["fill"], "#F28C00")
        self.assertEqual(polygon.attrib["stroke"], "#B85F00")
        points = [
            tuple(float(value) for value in point.split(","))
            for point in polygon.attrib["points"].split()
        ]
        marker_band = next(
            item for item in _elements(root, "marker-band") if item.attrib["data-marker"] == "TPOX"
        )
        marker_rect = marker_band.find("svg:rect", NS)
        marker_top = float(marker_rect.attrib["y"])
        marker_bottom = marker_top + float(marker_rect.attrib["height"])
        marker_right = float(marker_rect.attrib["x"]) + float(marker_rect.attrib["width"])
        self.assertEqual(min(y for _, y in points), marker_top)
        self.assertEqual(max(y for _, y in points), marker_bottom)
        self.assertGreaterEqual(marker_right - max(x for x, _ in points), 6.0)
        left_edge_angle = math.degrees(
            math.atan2(points[3][1] - points[0][1], points[3][0] - points[0][0])
        )
        self.assertAlmostEqual(
            float(ribbons[0].attrib["data-ribbon-angle"]),
            left_edge_angle,
            places=3,
        )
        self.assertIn(
            f"rotate({ribbons[0].attrib['data-ribbon-angle']}", ribbon_text.attrib["transform"]
        )
        legend_items = _elements(root, "marker-annotation-legend-item")
        self.assertEqual(len(legend_items), 1)
        legend_swatch = legend_items[0].find("svg:rect", NS)
        self.assertEqual(legend_swatch.attrib["fill"], "#F28C00")
        legend_text = legend_items[0].find(
            'svg:text[@data-legend-message="off-ladder-no-size"]', NS
        )
        self.assertEqual(
            legend_text.text,
            "Marker TPOX contains unpositioned off-ladder allele(s) without size information.",
        )

    def test_optional_visual_layers_can_be_disabled(self):
        svg = render_svg(
            self.positioned,
            options=SvgRenderOptions(
                show_grid=False, show_marker_bands=False, show_disclaimer=False
            ),
        )
        root = _root(svg)
        self.assertEqual(_elements(root, "horizontal-grid"), [])
        self.assertEqual(_elements(root, "marker-band"), [])
        self.assertEqual(_elements(root, "disclaimer"), [])
        self.assertEqual(len(_elements(root, "called-peak")), 43)

    def test_off_ladder_ribbon_stays_within_the_short_amel_marker_band(self):
        sample = SampleCall(
            "S",
            OrderedDict(
                {"Amelogenin": MarkerCall("Amelogenin", "VIC", (AlleleCall(1, "OL", 100),))}
            ),
        )
        root = _root(render_svg(sample, kit_name="GlobalFiler"))
        ribbon = next(
            item
            for item in _elements(root, "marker-annotation-ribbon")
            if item.attrib["data-marker"] == "Amelogenin"
        )
        polygon = ribbon.find("svg:polygon", NS)
        points = [
            tuple(float(value) for value in point.split(","))
            for point in polygon.attrib["points"].split()
        ]
        marker_band = next(
            item
            for item in _elements(root, "marker-band")
            if item.attrib["data-marker"] == "Amelogenin"
        )
        marker_rect = marker_band.find("svg:rect", NS)
        marker_left = float(marker_rect.attrib["x"])
        marker_top = float(marker_rect.attrib["y"])
        marker_right = marker_left + float(marker_rect.attrib["width"])
        marker_bottom = marker_top + float(marker_rect.attrib["height"])
        self.assertGreaterEqual(min(x for x, _ in points), marker_left)
        self.assertLessEqual(max(x for x, _ in points), marker_right - 6.0)
        self.assertEqual(min(y for _, y in points), marker_top)
        self.assertEqual(max(y for _, y in points), marker_bottom)
        ribbon_text = ribbon.find("svg:text", NS)
        self.assertIsNotNone(ribbon_text)
        self.assertEqual(ribbon_text.attrib["fill"], "#FFFFFF")

    def test_default_title_uses_only_the_sample_display_name(self):
        sample = SampleCall(
            "internal-id [file-1]",
            OrderedDict({"TPOX": MarkerCall("TPOX", "FAM", (AlleleCall(1, "8", 500),))}),
            display_name="Case sample 17",
        )
        root = _root(render_svg(sample, kit_name="GlobalFiler"))
        self.assertEqual(root.find("svg:title", NS).text, "Case sample 17")
        visible_title = root.find('.//svg:text[@class="document-title"]', NS)
        self.assertEqual(visible_title.text, "Case sample 17")
        self.assertNotIn("GlobalFiler", visible_title.text)
        metadata = json.loads(root.find("svg:metadata", NS).text)
        self.assertEqual(metadata["sample_id"], "internal-id [file-1]")
        self.assertEqual(metadata["sample_display_name"], "Case sample 17")

    def test_subtitle_uses_full_kit_name_and_manufacturer(self):
        sample = SampleCall(
            "S",
            OrderedDict({"TPOX": MarkerCall("TPOX", "FAM", (AlleleCall(1, "8", 500),))}),
        )
        root = _root(render_svg(sample, kit_name="GlobalFiler"))
        subtitle = root.find('.//svg:text[@class="document-subtitle"]', NS)
        self.assertEqual(
            subtitle.text,
            "Kit: GlobalFiler PCR Amplification Kit (Thermo Fisher Scientific) · "
            "nominal coordinate model 0.2 · called peaks: 1",
        )

    def test_custom_title_and_domain_are_applied(self):
        svg = render_svg(
            self.positioned,
            options=SvgRenderOptions(title="Custom title", x_min_bp=50, x_max_bp=500),
        )
        root = _root(svg)
        self.assertEqual(root.find("svg:title", NS).text, "Custom title")
        tick_labels = [element.text for element in _elements(root, "axis-label")]
        self.assertIn("50", tick_labels)
        self.assertIn("500", tick_labels)

    def test_rejects_invalid_xml_character_in_sample_id(self):
        sample = SampleCall(
            "bad\x00sample",
            OrderedDict({"TPOX": MarkerCall("TPOX", "FAM", (AlleleCall(1, "8", 500),))}),
        )
        with self.assertRaises(SvgRenderError):
            render_svg(sample, kit_name="GlobalFiler")

    def test_rejects_unknown_positioned_kit(self):
        invalid = replace(self.positioned, kit_name="UnknownKit")
        with self.assertRaises(SvgRenderError):
            render_svg(invalid)

    def test_rejects_coordinate_metadata_mismatch(self):
        invalid = replace(self.positioned, coordinate_model_version="9.9")
        with self.assertRaises(SvgRenderError):
            render_svg(invalid)

    def test_renderer_defensively_rejects_forged_negative_rfu(self):
        with mock.patch.object(PositionedPeak, "__post_init__", return_value=None):
            peak = replace(self.positioned.peaks[0], height=-1)
        invalid = replace(self.positioned, peaks=(peak, *self.positioned.peaks[1:]))
        with self.assertRaises(SvgRenderError):
            render_svg(invalid)

    def test_rejects_wrong_kit_dye_in_positioned_peak(self):
        peak = replace(self.positioned.peaks[0], dye="VIC")
        invalid = replace(self.positioned, peaks=(peak, *self.positioned.peaks[1:]))
        with self.assertRaises(SvgRenderError):
            render_svg(invalid)

    def test_renderer_defensively_rejects_forged_out_of_range_coordinate(self):
        with mock.patch.object(PositionedPeak, "__post_init__", return_value=None):
            peak = replace(self.positioned.peaks[0], coordinate_bp=Decimal("999"))
        invalid = replace(self.positioned, peaks=(peak, *self.positioned.peaks[1:]))
        with self.assertRaises(SvgRenderError):
            render_svg(invalid)

    def test_render_svg_matches_explicit_position_then_render(self):
        direct = render_svg(self.sample)
        explicit = render_svg(position_sample(self.sample))
        self.assertEqual(direct, explicit)


class RfuAxisScalingTests(unittest.TestCase):
    def test_per_channel_rfu_axis_rounds_up_to_readable_values(self):
        sample = SampleCall(
            "S-round",
            OrderedDict(
                {
                    "TPOX": MarkerCall(
                        "TPOX",
                        "FAM",
                        (AlleleCall(1, "8", 1397),),
                    )
                }
            ),
        )
        root = _root(render_svg(sample, kit_name="GlobalFiler"))
        fam_panel = next(
            panel
            for panel in root.findall('.//svg:g[@class="channel-panel"]', NS)
            if panel.attrib["data-dye"] == "FAM"
        )
        ticks = [
            int(node.text) for node in fam_panel.findall('.//svg:text[@class="rfu-label"]', NS)
        ]
        self.assertEqual(ticks, [1500, 750, 0])

    def test_existing_rfu_ticks_are_simple_fractions_of_the_axis_maximum(self):
        root = _root(render_svg(load_project(FIXTURES / "globalfiler_minimal.tsv").sample("S1")))
        for panel in root.findall('.//svg:g[@class="channel-panel"]', NS):
            ticks = [
                int(node.text) for node in panel.findall('.//svg:text[@class="rfu-label"]', NS)
            ]
            self.assertEqual(ticks[1], ticks[0] // 2)
            self.assertEqual(ticks[2], 0)


class SvgRenderOptionValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        project = load_project(FIXTURES / "globalfiler_minimal.tsv")
        cls.positioned = position_sample(project.sample("S1"))

    def assert_invalid(self, **changes):
        options = replace(SvgRenderOptions(), **changes)
        with self.assertRaises(SvgRenderError):
            render_svg(self.positioned, options=options)

    def test_rejects_too_small_width(self):
        self.assert_invalid(width=699)

    def test_rejects_too_small_channel_height(self):
        self.assert_invalid(channel_height=219)

    def test_rejects_boolean_as_integer_dimension(self):
        self.assert_invalid(width=True)

    def test_rejects_invalid_scale_mode(self):
        self.assert_invalid(rfu_scale_mode="unknown")

    def test_rejects_invalid_unpositioned_policy(self):
        self.assert_invalid(unpositioned_policy="unknown")

    def test_rejects_only_one_x_boundary(self):
        self.assert_invalid(x_min_bp=50)

    def test_rejects_reversed_x_domain(self):
        self.assert_invalid(x_min_bp=500, x_max_bp=50)

    def test_rejects_nonfinite_x_domain(self):
        self.assert_invalid(x_min_bp="NaN", x_max_bp=500)

    def test_rejects_invalid_peak_width(self):
        self.assert_invalid(peak_half_width_bp=0)

    def test_rejects_invalid_label_lane_count(self):
        self.assert_invalid(label_lanes=9)

    def test_rejects_empty_font_family(self):
        self.assert_invalid(font_family="  ")

    def test_rejects_non_boolean_visual_option(self):
        self.assert_invalid(show_grid="false")

    def test_rejects_label_lanes_that_do_not_fit_channel_height(self):
        self.assert_invalid(label_lanes=8)

    def test_channel_height_boundary_matches_shared_label_geometry(self):
        lanes = SvgRenderOptions().label_lanes
        minimum = _minimum_channel_height(lanes)
        self.assert_invalid(channel_height=minimum - 1)
        render_svg(self.positioned, options=SvgRenderOptions(channel_height=minimum))

    def test_rejects_unsafe_font_css(self):
        self.assert_invalid(font_family="Arial; url(https://example.invalid)")

    def test_rejects_invalid_xml_control_character_in_title(self):
        self.assert_invalid(title="bad\x00title")

    def test_rejects_domain_that_excludes_called_peaks(self):
        self.assert_invalid(x_min_bp=300, x_max_bp=500)


if __name__ == "__main__":
    unittest.main()
