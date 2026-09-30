"""Regressions for render-time validation of positioned samples.

Render-time validation has two deliberate layers. It checks what constructors cannot
know (kit dyes and markers, XML-safe text), and it re-checks heights, ranges and
coordinates as defense in depth: a positioned sample that bypassed its constructors
must fail loudly instead of rendering a plausible but wrong image.
"""

from __future__ import annotations

import unittest
from dataclasses import replace
from decimal import Decimal
from unittest import mock

from epg_renderer import position_sample
from epg_renderer.domain import PeakHeightMode
from epg_renderer.models import AlleleCall, MarkerCall, SampleCall
from epg_renderer.positions import PeakCoordinateSource, PositionedPeak, PositionedSample
from epg_renderer.render_document import render_positioned_sample_svg
from epg_renderer.render_options import SvgRenderError
from epg_renderer.render_svg import _validate_positioned_sample

KIT = "GlobalFiler"
MARKER = "D3S1358"


def _positioned() -> tuple[PositionedSample, PositionedPeak]:
    sample = SampleCall("S1", {MARKER: MarkerCall(MARKER, None, (AlleleCall(1, "15", 1200),))})
    positioned = position_sample(sample, kit_name=KIT)
    return positioned, positioned.peaks[0]


class KitDependentRenderValidationTests(unittest.TestCase):
    def test_renderer_rejects_facts_only_the_kit_can_check(self) -> None:
        positioned, peak = _positioned()
        cases = {
            "unknown dye": replace(peak, dye="XYZ"),
            "marker not defined": replace(peak, marker="FOO1"),
            "is required": replace(peak, dye="VIC"),
            "not permitted in XML": replace(peak, allele="1\x015"),
        }
        for message, bad_peak in cases.items():
            with self.subTest(message=message), self.assertRaisesRegex(SvgRenderError, message):
                render_positioned_sample_svg(replace(positioned, peaks=(bad_peak,)))

    def test_renderer_rejects_xml_invalid_sample_identifier(self) -> None:
        positioned, _ = _positioned()
        with self.assertRaisesRegex(SvgRenderError, "not permitted in XML"):
            render_positioned_sample_svg(replace(positioned, sample_id="S\x01"))


class DefenseInDepthTests(unittest.TestCase):
    def test_constructors_reject_every_state_the_renderer_re_checks(self) -> None:
        positioned, peak = _positioned()
        range_max = peak.marker_range_max_bp
        cases = {
            "negative height": lambda: replace(peak, height=-1),
            "height above maximum": lambda: replace(peak, height=40_000),
            "missing RFU height": lambda: replace(positioned, peaks=(replace(peak, height=None),)),
            "RFU value in uniform mode": lambda: replace(
                positioned, height_mode=PeakHeightMode.UNIFORM
            ),
            "non-finite range minimum": lambda: replace(peak, marker_range_min_bp=Decimal("NaN")),
            "non-finite range maximum": lambda: replace(
                peak, marker_range_max_bp=Decimal("Infinity")
            ),
            "empty range": lambda: replace(peak, marker_range_min_bp=range_max),
            "coordinate marked unpositioned": lambda: replace(
                peak, coordinate_source=PeakCoordinateSource.UNPOSITIONED
            ),
            "non-finite coordinate": lambda: replace(peak, coordinate_bp=Decimal("NaN")),
            "coordinate outside range": lambda: replace(peak, coordinate_bp=range_max + 1),
            "positioned source without coordinate": lambda: replace(peak, coordinate_bp=None),
            "empty sample identifier": lambda: replace(positioned, sample_id=" "),
        }
        for name, build in cases.items():
            with self.subTest(case=name), self.assertRaises(ValueError):
                build()

    def test_renderer_rejects_forged_coordinate_outside_its_marker_band(self) -> None:
        positioned, peak = _positioned()
        with mock.patch.object(PositionedPeak, "__post_init__", return_value=None):
            forged = replace(peak, coordinate_bp=peak.marker_range_max_bp + 10)
        with self.assertRaisesRegex(SvgRenderError, "outside its marker range"):
            render_positioned_sample_svg(replace(positioned, peaks=(forged,)))

    def test_renderer_documents_its_deliberate_double_check(self) -> None:
        docstring = _validate_positioned_sample.__doc__ or ""
        self.assertIn("defense in depth", docstring)
        self.assertIn("deliberate", docstring)


if __name__ == "__main__":
    unittest.main()
