from __future__ import annotations

import math
import unittest
import xml.etree.ElementTree as ET
from functools import cache
from importlib.util import find_spec
from io import BytesIO
from itertools import pairwise
from pathlib import Path
from xml.sax.saxutils import escape

from epg_renderer.render_metrics import _LABEL_METRICS, _MARKER_LABEL_METRICS
from epg_renderer.render_svg import _fit_marker_label_text

RASTER_DEPENDENCIES_AVAILABLE = find_spec("cairosvg") is not None and find_spec("PIL") is not None

NS = {"svg": "http://www.w3.org/2000/svg"}
ROOT = Path(__file__).resolve().parents[1]
FONT_FAMILY = "Arial, Helvetica, sans-serif"
RASTER_SCALE = 4
PIXEL_TOLERANCE = 0.5


@unittest.skipUnless(RASTER_DEPENDENCIES_AVAILABLE, "Raster dependencies are not installed")
class IndependentRenderedTextGeometryTests(unittest.TestCase):
    @staticmethod
    @cache
    def _rendered_text_width(text: str, font_size: float, font_weight: int) -> float:
        import cairosvg
        from PIL import Image

        canvas_width = max(100, math.ceil(len(text) * font_size * 2 + 20))
        canvas_height = max(60, math.ceil(font_size * 4))
        baseline = font_size * 2.5
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{canvas_width}" height="{canvas_height}">'
            f'<text x="10" y="{baseline:g}" font-family="{FONT_FAMILY}" '
            f'font-size="{font_size:g}" font-weight="{font_weight}" fill="#000000">'
            f"{escape(text)}</text></svg>"
        )
        png = cairosvg.svg2png(
            bytestring=svg.encode("utf-8"),
            output_width=canvas_width * RASTER_SCALE,
            output_height=canvas_height * RASTER_SCALE,
        )
        if not isinstance(png, bytes):
            raise AssertionError("CairoSVG did not return PNG bytes.")
        with Image.open(BytesIO(png)) as image:
            bounds = image.getchannel("A").getbbox()
        if bounds is None:
            raise AssertionError(f"Rendered text {text!r} produced no visible pixels.")
        return (bounds[2] - bounds[0]) / RASTER_SCALE

    def test_fitted_marker_text_stays_inside_its_band(self) -> None:
        cases = (("WWWW", 39.5), ("D22S1045", 36.5))
        for source_text, band_width in cases:
            label, fitted_size = _fit_marker_label_text(source_text, band_width=band_width)
            font_size = fitted_size or _MARKER_LABEL_METRICS.font_size_px
            actual_width = self._rendered_text_width(label, font_size, 700)
            self.assertLessEqual(
                actual_width,
                band_width + PIXEL_TOLERANCE,
                msg=(
                    f"Rendered marker label {label!r} is {actual_width:.2f}px wide "
                    f"inside a {band_width:.2f}px band."
                ),
            )

    def test_ngm_detect_short_marker_labels_fit_inside_the_padded_bands(self) -> None:
        root = ET.parse(ROOT / "examples" / "ngm_detect_five_person_mixture_example.svg").getroot()
        expected = {"Yindel": "Y...", "Amelogenin": "A..."}
        found: set[str] = set()
        for band in root.findall('.//svg:g[@class="marker-band"]', NS):
            marker = band.attrib["data-marker"]
            if marker not in expected:
                continue
            rectangle = band.find("svg:rect", NS)
            label = band.find("svg:text", NS)
            self.assertIsNotNone(rectangle)
            self.assertIsNotNone(label)
            assert rectangle is not None and label is not None
            found.add(marker)
            self.assertEqual(label.text, expected[marker])
            font_size = float(label.attrib["font-size"])
            self.assertEqual(font_size, _MARKER_LABEL_METRICS.fallback_font_size_px)
            actual_width = self._rendered_text_width(label.text or "", font_size, 700)
            available_width = (
                float(rectangle.attrib["width"]) - _MARKER_LABEL_METRICS.horizontal_padding_px
            )
            self.assertLessEqual(
                actual_width,
                available_width + PIXEL_TOLERANCE,
                msg=(
                    f"Rendered {marker} label {label.text!r} is {actual_width:.2f}px wide "
                    f"but only {available_width:.2f}px is available after padding."
                ),
            )
        self.assertEqual(found, set(expected))

    def test_example_text_fits_boxes_and_actual_glyphs_do_not_overlap(self) -> None:
        root = ET.parse(ROOT / "examples" / "globalfiler_example.svg").getroot()
        for band in root.findall('.//svg:g[@class="marker-band"]', NS):
            rectangle = band.find("svg:rect", NS)
            label = band.find("svg:text", NS)
            self.assertIsNotNone(rectangle)
            self.assertIsNotNone(label)
            assert rectangle is not None and label is not None
            font_size = float(
                label.attrib.get("font-size", str(_MARKER_LABEL_METRICS.font_size_px))
            )
            actual_width = self._rendered_text_width(label.text or "", font_size, 700)
            self.assertLessEqual(actual_width, float(rectangle.attrib["width"]) + PIXEL_TOLERANCE)

        for channel in root.findall('.//svg:g[@class="channel-panel"]', NS):
            intervals_by_lane: dict[int, list[tuple[float, float, str]]] = {}
            for peak in channel.findall('.//svg:g[@class="called-peak"]', NS):
                label = peak.find('svg:text[@class="peak-label"]', NS)
                self.assertIsNotNone(label)
                assert label is not None
                lines = label.findall("svg:tspan", NS)
                self.assertEqual(len(lines), 2)
                allele = lines[0].text or ""
                rfu = lines[1].text or ""
                actual_width = max(
                    self._rendered_text_width(allele, _LABEL_METRICS.allele_font_size_px, 600),
                    self._rendered_text_width(rfu, _LABEL_METRICS.height_font_size_px, 400),
                )
                box_width = float(peak.attrib["data-label-box-width"])
                self.assertLessEqual(actual_width, box_width + PIXEL_TOLERANCE)
                centre = float(peak.attrib["data-label-box-x"]) + box_width / 2
                lane = int(peak.attrib["data-label-lane"])
                intervals_by_lane.setdefault(lane, []).append(
                    (centre - actual_width / 2, centre + actual_width / 2, allele)
                )

            for intervals in intervals_by_lane.values():
                intervals.sort()
                for current, following in pairwise(intervals):
                    self.assertLessEqual(
                        current[1],
                        following[0] + PIXEL_TOLERANCE,
                        msg=f"Rendered labels {current[2]!r} and {following[2]!r} overlap.",
                    )


if __name__ == "__main__":
    unittest.main()
