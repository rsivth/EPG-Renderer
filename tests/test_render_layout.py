from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from epg_renderer import (
    load_kit,
    load_project,
    render_svg,
)
from epg_renderer.domain import PeakHeightMode
from epg_renderer.manual_profile import ManualMarkerEntry, build_manual_profile

FIXTURES = Path(__file__).with_name("fixtures")


def _root(svg: str) -> ET.Element:
    return ET.fromstring(svg)


def _elements(root: ET.Element, class_name: str) -> list[ET.Element]:
    return [
        element for element in root.iter() if class_name in element.attrib.get("class", "").split()
    ]


class LayoutDesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gf_sample = load_project(FIXTURES / "globalfiler_minimal.tsv").sample("S1")
        cls.svg = render_svg(cls.gf_sample)
        cls.root = _root(cls.svg)

    def test_channel_panels_have_white_background_and_unchanged_outline(self):
        style = next(element for element in self.root if element.tag.endswith("style"))
        self.assertIsNotNone(style.text)
        self.assertIn(
            ".panel-background { fill: #FFFFFF; stroke: #DADCE0; stroke-width: 0.9; }",
            style.text,
        )
        for channel in _elements(self.root, "channel-panel"):
            panel = next(
                element
                for element in channel
                if "panel-background" in element.attrib.get("class", "")
            )
            self.assertEqual(panel.attrib["class"], "panel-background")

    def test_channel_labels_are_left_aligned_with_padding_inside_panel(self):
        for channel in _elements(self.root, "channel-panel"):
            panel = next(
                element
                for element in channel
                if "panel-background" in element.attrib.get("class", "")
            )
            label = next(
                element for element in channel if "channel-label" in element.attrib.get("class", "")
            )
            self.assertEqual(label.attrib["text-anchor"], "start")
            self.assertEqual(float(label.attrib["x"]) - float(panel.attrib["x"]), 10.0)

    def test_long_esi_dye_label_starts_inside_channel_panel(self):
        kit = load_kit("PowerPlex ESI 17 Fast")
        marker = kit.kit.marker("D3S1358")
        profile = build_manual_profile(
            "ESI label check",
            kit.kit.name,
            {marker.name: ManualMarkerEntry(marker.name, (marker.ladder_alleles[0],), (500,))},
            height_mode=PeakHeightMode.RFU,
        )
        root = _root(render_svg(profile.to_sample_call(), kit_name=profile.kit_name))
        channel = next(
            element
            for element in _elements(root, "channel-panel")
            if element.attrib["data-channel-label"] == "Fluorescein"
        )
        panel = next(
            element for element in channel if "panel-background" in element.attrib.get("class", "")
        )
        label = next(
            element for element in channel if "channel-label" in element.attrib.get("class", "")
        )
        self.assertEqual(label.text, "Fluorescein")
        self.assertEqual(label.attrib["text-anchor"], "start")
        self.assertGreater(float(label.attrib["x"]), float(panel.attrib["x"]))
        self.assertEqual(float(label.attrib["x"]) - float(panel.attrib["x"]), 10.0)

    def test_marker_boxes_are_light_grey_with_black_outline(self):
        for band in _elements(self.root, "marker-band"):
            rect = next(element for element in band if element.tag.endswith("rect"))
            self.assertEqual(rect.attrib["fill"], "#F3F4F6")
            self.assertEqual(rect.attrib["stroke"], "#000000")

    def test_marker_names_are_black_in_every_channel(self):
        for band in _elements(self.root, "marker-band"):
            text = next(element for element in band if element.tag.endswith("text"))
            self.assertEqual(text.attrib["fill"], "#000000")

    def test_every_called_peak_has_a_white_black_allele_box(self):
        peaks = _elements(self.root, "called-peak")
        self.assertEqual(len(peaks), 43)
        for peak in peaks:
            boxes = [
                element for element in peak if "allele-label-box" in element.attrib.get("class", "")
            ]
            self.assertEqual(len(boxes), 1)
            self.assertEqual(boxes[0].attrib["fill"], "#FFFFFF")
            self.assertEqual(boxes[0].attrib["stroke"], "#000000")

    def test_every_allele_label_is_black(self):
        for peak in _elements(self.root, "called-peak"):
            label = next(element for element in peak if element.tag.endswith("text"))
            self.assertEqual(label.attrib["fill"], "#000000")

    def test_peak_shapes_retain_channel_colors(self):
        expected = {
            "FAM": "#0067C5",
            "VIC": "#008B45",
            "NED": "#A87800",
            "TAZ": "#C62828",
            "SID": "#7B1FA2",
        }
        for channel in _elements(self.root, "channel-panel"):
            paths = [element for element in channel.iter() if element.tag.endswith("path")]
            self.assertTrue(paths)
            self.assertTrue(
                all(path.attrib["stroke"] == expected[channel.attrib["data-dye"]] for path in paths)
            )

    def test_layout_remains_within_channel_panel(self):
        for channel in _elements(self.root, "channel-panel"):
            panel = next(
                element
                for element in channel
                if "panel-background" in element.attrib.get("class", "")
            )
            bottom = float(panel.attrib["y"]) + float(panel.attrib["height"])
            for box in _elements(channel, "allele-label-box"):
                self.assertLessEqual(
                    float(box.attrib["y"]) + float(box.attrib["height"]), bottom + 1
                )

    def test_v04_design_is_deterministic(self):
        self.assertEqual(self.svg, render_svg(self.gf_sample))


class NgmRenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sample = load_project(FIXTURES / "ngm_minimal.tsv").sample("N1")
        cls.svg = render_svg(sample)
        cls.root = _root(cls.svg)

    def test_ngm_renders_four_channels_in_order(self):
        self.assertEqual(
            [element.attrib["data-dye"] for element in _elements(self.root, "channel-panel")],
            ["FAM", "VIC", "NED", "PET"],
        )

    def test_ngm_renders_all_16_marker_boxes(self):
        self.assertEqual(len(_elements(self.root, "marker-band")), 16)

    def test_ngm_renders_all_and_only_32_called_peaks(self):
        self.assertEqual(len(_elements(self.root, "called-peak")), 32)

    def test_ngm_default_height_reflects_four_channels(self):
        self.assertEqual(self.root.attrib["height"], "1132")
        self.assertEqual(self.root.attrib["viewBox"], "0 0 1600 1132")


if __name__ == "__main__":
    unittest.main()
