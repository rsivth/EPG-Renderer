from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path

from epg_renderer import (
    load_project,
    position_sample,
    render_svg,
)
from epg_renderer.render_layout import estimate_text_width
from epg_renderer.render_metrics import (
    _LABEL_LAYOUT_PARAMETERS,
    _LABEL_METRICS,
    _MARKER_LABEL_METRICS,
    _TYPOGRAPHY_METRICS,
)
from epg_renderer.render_options import SvgRenderOptions

FIXTURES = Path(__file__).with_name("fixtures")


def _root(svg: str) -> ET.Element:
    return ET.fromstring(svg)


def _elements(root: ET.Element, class_name: str) -> list[ET.Element]:
    return [
        element for element in root.iter() if class_name in element.attrib.get("class", "").split()
    ]


def _boxes_overlap(a: ET.Element, b: ET.Element) -> bool:
    ax = float(a.attrib["x"])
    ay = float(a.attrib["y"])
    aw = float(a.attrib["width"])
    ah = float(a.attrib["height"])
    bx = float(b.attrib["x"])
    by = float(b.attrib["y"])
    bw = float(b.attrib["width"])
    bh = float(b.attrib["height"])
    return ax < bx + bw and bx < ax + aw and (ay < by + bh) and (by < ay + ah)


class RenderingDesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sample = load_project(FIXTURES / "globalfiler_minimal.tsv").sample("S1")
        cls.svg = render_svg(cls.sample)
        cls.root = _root(cls.svg)

    def test_each_channel_maximum_is_a_rounded_value_at_or_above_highest_peak(self):
        for channel in _elements(self.root, "channel-panel"):
            peaks = _elements(channel, "called-peak")
            if peaks:
                axis_max = int(channel.attrib["data-rfu-max"])
                highest_peak = max(int(peak.attrib["data-rfu"]) for peak in peaks)
                self.assertGreaterEqual(axis_max, highest_peak)
                self.assertIn(
                    axis_max,
                    {100, 150, 200, 250, 300, 400, 500, 750, 800}
                    | {value * 10 for value in (10, 15, 20, 25, 30, 40, 50, 75, 80)}
                    | {value * 100 for value in (10, 15, 20, 25, 30, 40, 50, 75, 80)},
                )

    def test_highest_peak_is_scaled_from_the_rounded_axis_maximum(self):
        for channel in _elements(self.root, "channel-panel"):
            peaks = _elements(channel, "called-peak")
            if not peaks:
                continue
            highest = max(peaks, key=lambda peak: int(peak.attrib["data-rfu"]))
            signal_top = float(channel.attrib["data-signal-top"])
            signal_bottom = float(channel.attrib["data-baseline-y"])
            axis_max = int(channel.attrib["data-rfu-max"])
            expected_y = signal_bottom - (int(highest.attrib["data-rfu"]) / axis_max) * (
                signal_bottom - signal_top
            )
            self.assertAlmostEqual(
                float(highest.attrib["data-y-px"]),
                expected_y,
                places=3,
            )

    def test_vertical_grid_is_bounded_by_the_rfu_plot(self):
        for channel in _elements(self.root, "channel-panel"):
            signal_top = float(channel.attrib["data-signal-top"])
            signal_bottom = float(channel.attrib["data-baseline-y"])
            horizontal_grid = _elements(channel, "horizontal-grid")
            vertical_grid = _elements(channel, "vertical-grid")

            self.assertTrue(horizontal_grid)
            self.assertTrue(vertical_grid)
            self.assertIn(signal_top, {float(line.attrib["y1"]) for line in horizontal_grid})
            for line in vertical_grid:
                self.assertEqual(float(line.attrib["y1"]), signal_top)
                self.assertEqual(float(line.attrib["y2"]), signal_bottom)

    def test_rfu_label_contains_only_numeric_value(self):
        for peak in _elements(self.root, "called-peak"):
            label = next(element for element in peak if element.tag.endswith("text"))
            tspans = [element for element in label if element.tag.endswith("tspan")]
            self.assertEqual(tspans[1].text, peak.attrib["data-rfu"])
            self.assertNotIn("RFU", "".join(peak.itertext()))

    def test_peak_fill_is_white_and_outline_is_channel_colored(self):
        expected = {
            "FAM": "#0067C5",
            "VIC": "#008B45",
            "NED": "#A87800",
            "TAZ": "#C62828",
            "SID": "#7B1FA2",
        }
        for peak in _elements(self.root, "called-peak"):
            path = next(element for element in peak if element.tag.endswith("path"))
            self.assertEqual(path.attrib["fill"], "#FFFFFF")
            self.assertEqual(path.attrib["stroke"], expected[peak.attrib["data-dye"]])
            self.assertNotIn("fill-opacity", path.attrib)

    def test_marker_label_style_uses_shared_default_size_without_letter_spacing(self):
        style = next(element for element in self.root if element.tag.endswith("style"))
        css = style.text or ""
        self.assertIn(
            f".marker-label {{ font-size: {_MARKER_LABEL_METRICS.font_size_px:g}px;",
            css,
        )
        marker_rule = next(line for line in css.splitlines() if line.startswith(".marker-label "))
        self.assertNotIn("letter-spacing", marker_rule)

    def test_peak_outline_uses_the_expected_subtle_emphasis(self):
        for peak in _elements(self.root, "called-peak"):
            path = next(element for element in peak if element.tag.endswith("path"))
            self.assertEqual(path.attrib["stroke-width"], "1.8")

    def test_axis_and_subtitle_typography_uses_shared_metrics(self):
        style = next(element for element in self.root if element.tag.endswith("style"))
        css = style.text or ""
        self.assertIn(
            f".document-title {{ font-size: {_TYPOGRAPHY_METRICS.document_title_font_size_px:g}px; "
            f"font-weight: 700; fill: {_TYPOGRAPHY_METRICS.primary_text_color};",
            css,
        )
        self.assertIn(
            f".document-subtitle {{ font-size: {_TYPOGRAPHY_METRICS.document_subtitle_font_size_px:g}px; "
            f"fill: {_TYPOGRAPHY_METRICS.primary_text_color};",
            css,
        )
        self.assertIn(
            f".axis-label, .axis-unit, .rfu-label {{ font-size: {_TYPOGRAPHY_METRICS.axis_text_font_size_px:g}px; "
            f"fill: {_TYPOGRAPHY_METRICS.secondary_text_color};",
            css,
        )
        self.assertEqual(_TYPOGRAPHY_METRICS.document_subtitle_font_size_px, 11.0)
        self.assertEqual(_TYPOGRAPHY_METRICS.axis_text_font_size_px, 10.0)
        self.assertNotEqual(
            _TYPOGRAPHY_METRICS.primary_text_color,
            _TYPOGRAPHY_METRICS.secondary_text_color,
        )

    def test_peak_label_metrics_are_derived_from_shared_layout_parameters(self):
        self.assertEqual(_LABEL_METRICS.allele_font_size_px, 11.5)
        self.assertEqual(_LABEL_METRICS.height_font_size_px, 10.0)
        self.assertEqual(
            _LABEL_METRICS.allele_baseline_offset_px,
            _LABEL_LAYOUT_PARAMETERS.top_padding_px + 11,
        )
        self.assertEqual(
            _LABEL_METRICS.height_line_offset_px,
            _LABEL_LAYOUT_PARAMETERS.line_gap_px + 10,
        )
        self.assertEqual(
            _LABEL_METRICS.rfu_box_height_px,
            _LABEL_METRICS.allele_baseline_offset_px
            + _LABEL_METRICS.height_line_offset_px
            + _LABEL_LAYOUT_PARAMETERS.bottom_padding_px
            + 1,
        )
        self.assertEqual(
            _LABEL_METRICS.lane_height_px,
            _LABEL_METRICS.rfu_box_height_px + _LABEL_LAYOUT_PARAMETERS.lane_gap_px,
        )

    def test_peak_label_fonts_boxes_and_width_measurement_share_current_metrics(self):
        style = next(element for element in self.root if element.tag.endswith("style"))
        self.assertIn(
            f".peak-label {{ font-size: {_LABEL_METRICS.allele_font_size_px:g}px;",
            style.text or "",
        )
        self.assertIn(
            f".height-label {{ font-size: {_LABEL_METRICS.height_font_size_px:g}px;",
            style.text or "",
        )
        for peak in _elements(self.root, "called-peak"):
            box = next(
                element
                for element in peak
                if "allele-label-box" in element.attrib.get("class", "").split()
            )
            expected_width = (
                max(
                    estimate_text_width(
                        peak.attrib["data-allele"], _LABEL_METRICS.allele_font_size_px
                    ),
                    estimate_text_width(
                        peak.attrib["data-rfu"], _LABEL_METRICS.height_font_size_px
                    ),
                )
                + _LABEL_METRICS.horizontal_padding_px
            )
            self.assertAlmostEqual(float(box.attrib["width"]), expected_width, places=3)
            self.assertEqual(int(box.attrib["height"]), _LABEL_METRICS.rfu_box_height_px)

    def test_fixture_label_boxes_do_not_overlap(self):
        for channel in _elements(self.root, "channel-panel"):
            boxes = _elements(channel, "allele-label-box")
            for index, box in enumerate(boxes):
                for other in boxes[index + 1 :]:
                    self.assertFalse(_boxes_overlap(box, other))

    def test_connector_layer_is_painted_before_all_label_boxes(self):
        for channel in _elements(self.root, "channel-panel"):
            children = list(channel)
            connector_index = next(
                (
                    index
                    for index, element in enumerate(children)
                    if "connector-layer" in element.attrib.get("class", "").split()
                )
            )
            peak_index = next(
                (
                    index
                    for index, element in enumerate(children)
                    if "peak-and-label-layer" in element.attrib.get("class", "").split()
                )
            )
            self.assertLess(connector_index, peak_index)

    def test_every_connector_starts_at_baseline_and_ends_at_box_top(self):
        for channel in _elements(self.root, "channel-panel"):
            baseline_y = float(channel.attrib["data-baseline-y"])
            peaks = {
                peak.attrib["data-peak-index"]: peak for peak in _elements(channel, "called-peak")
            }
            for connector in _elements(channel, "allele-label-connector"):
                peak = peaks[connector.attrib["data-peak-index"]]
                self.assertEqual(float(connector.attrib["y1"]), baseline_y)
                self.assertEqual(
                    float(connector.attrib["y2"]), float(peak.attrib["data-label-box-y"])
                )

    def test_fourteen_allele_marker_grows_downward_without_label_overlap(self):
        positioned = position_sample(self.sample)
        source_peak = positioned.peaks[0]
        dense_peaks = tuple(
            replace(source_peak, allele_index=index + 1, allele=f"15.{index}", height=1000 - index)
            for index in range(14)
        )
        dense = replace(positioned, peaks=dense_peaks)
        options = SvgRenderOptions(label_lanes=1)
        root = _root(render_svg(dense, options=options))
        fam = next(
            channel
            for channel in _elements(root, "channel-panel")
            if channel.attrib["data-dye"] == "FAM"
        )
        expected_height = options.channel_height + 13 * _LABEL_METRICS.lane_height_px
        self.assertEqual(int(fam.attrib["data-label-lanes"]), 14)
        self.assertEqual(int(fam.attrib["data-panel-height"]), expected_height)

        panel = next(
            element
            for element in fam
            if "panel-background" in element.attrib.get("class", "").split()
        )
        panel_bottom = float(panel.attrib["y"]) + float(panel.attrib["height"])
        boxes = _elements(fam, "allele-label-box")
        self.assertEqual(len(boxes), 14)
        self.assertEqual(len({float(box.attrib["y"]) for box in boxes}), 14)
        for index, box in enumerate(boxes):
            self.assertLessEqual(
                float(box.attrib["y"]) + float(box.attrib["height"]),
                panel_bottom + 1,
            )
            for other in boxes[index + 1 :]:
                self.assertFalse(_boxes_overlap(box, other))
        self.assertTrue(
            all(
                peak.attrib["data-label-collision"] == "false"
                for peak in _elements(fam, "called-peak")
            )
        )


if __name__ == "__main__":
    unittest.main()
