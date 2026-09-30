"""Regressions for the segmented channel baseline.

Each channel baseline is drawn as non-overlapping segments that leave gaps under peak
footprints. A channel without called peaks must receive exactly one full-width segment,
not two identical ones.
"""

from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET
from itertools import pairwise

from epg_renderer import render_svg
from epg_renderer.models import AlleleCall, MarkerCall, SampleCall
from epg_renderer.render_options import SvgRenderOptions

NS = {"svg": "http://www.w3.org/2000/svg"}
KIT = "GlobalFiler"
MARKER = "D3S1358"


def _channels() -> list[ET.Element]:
    call = AlleleCall(allele_index=1, allele="15", height=1200)
    sample = SampleCall("S1", {MARKER: MarkerCall(MARKER, None, (call,))})
    root = ET.fromstring(render_svg(sample, kit_name=KIT))
    return root.findall('.//svg:g[@class="channel-panel"]', NS)


def _segments(channel: ET.Element) -> list[tuple[float, float]]:
    lines = channel.findall(
        './/svg:g[@class="segmented-baseline"]/svg:line[@class="axis-line channel-baseline-segment"]',
        NS,
    )
    return [(float(line.attrib["x1"]), float(line.attrib["x2"])) for line in lines]


def _has_peaks(channel: ET.Element) -> bool:
    return bool(channel.findall('.//svg:g[@class="called-peak"]', NS))


class BaselineSegmentTests(unittest.TestCase):
    def setUp(self) -> None:
        options = SvgRenderOptions()
        self.plot_left = float(options.left_margin)
        self.plot_right = float(options.width - options.right_margin)
        self.channels = _channels()

    def test_empty_channel_has_exactly_one_full_width_segment(self) -> None:
        empty = [channel for channel in self.channels if not _has_peaks(channel)]
        self.assertTrue(empty)
        for channel in empty:
            with self.subTest(dye=channel.attrib["data-dye"]):
                self.assertEqual(_segments(channel), [(self.plot_left, self.plot_right)])

    def test_no_channel_contains_overlapping_segments(self) -> None:
        for channel in self.channels:
            with self.subTest(dye=channel.attrib["data-dye"]):
                segments = sorted(_segments(channel))
                for (_, previous_end), (next_start, _) in pairwise(segments):
                    self.assertLess(previous_end, next_start)

    def test_channel_with_one_peak_leaves_one_gap(self) -> None:
        populated = [channel for channel in self.channels if _has_peaks(channel)]
        self.assertEqual(len(populated), 1)
        segments = _segments(populated[0])
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0][0], self.plot_left)
        self.assertEqual(segments[-1][1], self.plot_right)


if __name__ == "__main__":
    unittest.main()
