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
from epg_renderer.render_metrics import _LABEL_METRICS
from epg_renderer.render_options import (
    SvgRenderOptions,
    YellowChannelMode,
)

FIXTURES = Path(__file__).with_name("fixtures")


def elements(root, cls):
    return [e for e in root.iter() if cls in e.attrib.get("class", "").split()]


class ChannelRenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sample = load_project(FIXTURES / "globalfiler_minimal.tsv").sample("S1")

    def test_yellow_channel_default_and_black_override(self):
        default = ET.fromstring(render_svg(self.sample))
        black = ET.fromstring(
            render_svg(
                self.sample, options=SvgRenderOptions(yellow_channel_mode=YellowChannelMode.BLACK)
            )
        )
        default_ned = next(
            c for c in elements(default, "channel-panel") if c.attrib["data-dye"] == "NED"
        )
        black_ned = next(
            c for c in elements(black, "channel-panel") if c.attrib["data-dye"] == "NED"
        )
        self.assertNotEqual(default_ned.attrib["data-display-color"], "#202124")
        self.assertEqual(black_ned.attrib["data-display-color"], "#202124")
        self.assertTrue(
            all(p.attrib["stroke"] == "#202124" for p in elements(black_ned, "allele-peak-shape"))
        )

    def test_label_has_balanced_top_padding(self):
        root = ET.fromstring(render_svg(self.sample))
        for peak in elements(root, "called-peak"):
            box_y = float(peak.attrib["data-label-box-y"])
            box_h = float(peak.attrib["data-label-box-height"])
            text = next(e for e in peak if e.tag.endswith("text"))
            self.assertEqual(box_h, float(_LABEL_METRICS.rfu_box_height_px))
            self.assertAlmostEqual(
                float(text.attrib["y"]) - box_y,
                float(_LABEL_METRICS.allele_baseline_offset_px),
            )

    def test_tick_number_is_omitted_when_connector_crosses_it(self):
        positioned = position_sample(self.sample)
        peak = replace(positioned.peaks[0], coordinate_bp=__import__("decimal").Decimal("100"))
        root = ET.fromstring(render_svg(replace(positioned, peaks=(peak,))))
        omissions = elements(root, "axis-label-omission")
        self.assertTrue(
            any(
                o.attrib.get("data-tick") == "100"
                and o.attrib.get("data-reason") == "connector-collision"
                for o in omissions
            )
        )
        fam = next(c for c in elements(root, "channel-panel") if c.attrib["data-dye"] == "FAM")
        labels = [e.text for e in elements(fam, "axis-label")]
        self.assertNotIn("100", labels)

    def test_connectors_are_behind_all_opaque_label_boxes(self):
        root = ET.fromstring(render_svg(self.sample))
        for channel in elements(root, "channel-panel"):
            children = list(channel)
            connector = next(
                (
                    i
                    for i, e in enumerate(children)
                    if "connector-layer" in e.attrib.get("class", "").split()
                )
            )
            labels = next(
                (
                    i
                    for i, e in enumerate(children)
                    if "peak-and-label-layer" in e.attrib.get("class", "").split()
                )
            )
            self.assertLess(connector, labels)
            self.assertTrue(
                all(
                    box.attrib["fill"] == "#FFFFFF" for box in elements(channel, "allele-label-box")
                )
            )


if __name__ == "__main__":
    unittest.main()
