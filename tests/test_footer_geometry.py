"""Regressions for footer text inside the SVG document.

Footer height calculation, footer drawing and option validation share one set of
footer metrics. No accepted option combination may place disclaimer, warning or legend
text on or below the lower document edge.
"""

from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET

from epg_renderer import render_svg
from epg_renderer.models import AlleleCall, MarkerCall, SampleCall
from epg_renderer.render_options import SvgRenderError, SvgRenderOptions, validate_svg_options

SVG = "{http://www.w3.org/2000/svg}"
KIT = "GlobalFiler"
FOOTER_TEXT_CLASSES = frozenset({"disclaimer", "warning", "legend-heading", "legend-text"})
DESCENDER_ROOM_PX = 4.0
OFF_LADDER_MARKERS = ("vWA", "D16S539", "CSF1PO")


def _sample(off_ladder_markers: int, omitted_peak: bool) -> SampleCall:
    calls = [AlleleCall(1, "15", 1200)]
    if omitted_peak:
        calls.append(AlleleCall(2, "X9", 700))
    markers = {"D3S1358": MarkerCall("D3S1358", None, tuple(calls))}
    for marker in OFF_LADDER_MARKERS[:off_ladder_markers]:
        markers[marker] = MarkerCall(marker, None, (AlleleCall(1, "OL", 500),))
    return SampleCall("S1", markers)


def _footer_texts(options: SvgRenderOptions, sample: SampleCall) -> tuple[float, list[ET.Element]]:
    svg = render_svg(sample, kit_name=KIT, strict_positioning=False, options=options)
    root = ET.fromstring(svg)
    texts = [
        node for node in root.iter(f"{SVG}text") if node.attrib.get("class") in FOOTER_TEXT_CLASSES
    ]
    return float(root.attrib["height"]), texts


class FooterGeometryTests(unittest.TestCase):
    def test_footer_below_58_px_is_rejected_when_the_disclaimer_is_shown(self) -> None:
        with self.assertRaisesRegex(SvgRenderError, "footer_height must be at least 58"):
            validate_svg_options(SvgRenderOptions(footer_height=57, show_disclaimer=True))

    def test_footer_of_58_px_is_accepted_with_disclaimer(self) -> None:
        validate_svg_options(SvgRenderOptions(footer_height=58, show_disclaimer=True))

    def test_footer_of_30_px_is_accepted_without_disclaimer(self) -> None:
        validate_svg_options(SvgRenderOptions(footer_height=30, show_disclaimer=False))

    def test_no_accepted_option_combination_clips_footer_text(self) -> None:
        for footer_height in (30, 40, 47, 57, 58, 70):
            for show_disclaimer in (True, False):
                options = SvgRenderOptions(
                    footer_height=footer_height,
                    show_disclaimer=show_disclaimer,
                    unpositioned_policy="omit",
                )
                try:
                    validate_svg_options(options)
                except SvgRenderError:
                    continue
                for off_ladder_markers in (0, 3):
                    for omitted_peak in (False, True):
                        with self.subTest(
                            footer_height=footer_height,
                            disclaimer=show_disclaimer,
                            legend_lines=off_ladder_markers,
                            omitted_peak=omitted_peak,
                        ):
                            height, texts = _footer_texts(
                                options, _sample(off_ladder_markers, omitted_peak)
                            )
                            classes = [node.attrib["class"] for node in texts]
                            self.assertEqual(classes.count("disclaimer"), 2 * show_disclaimer)
                            self.assertEqual(classes.count("warning"), int(omitted_peak))
                            self.assertEqual(classes.count("legend-text"), off_ladder_markers)
                            overflow = [
                                f"{node.attrib['class']} at y={node.attrib['y']} "
                                f"(height {height:g})"
                                for node in texts
                                if float(node.attrib["y"]) + DESCENDER_ROOM_PX > height
                            ]
                            self.assertEqual(overflow, [])


if __name__ == "__main__":
    unittest.main()
