from __future__ import annotations

import json
import unittest
import xml.etree.ElementTree as ET
from collections import OrderedDict
from dataclasses import MISSING, fields
from decimal import Decimal

from epg_renderer import position_sample, render_svg
from epg_renderer.models import AlleleCall, MarkerCall, SampleCall
from epg_renderer.positions import PositionedPeak

NS = {"svg": "http://www.w3.org/2000/svg"}


def _sample(*alleles: AlleleCall) -> SampleCall:
    return SampleCall(
        "coordinate-provenance",
        OrderedDict({"TPOX": MarkerCall("TPOX", "FAM", alleles)}),
    )


def _root(sample: SampleCall) -> ET.Element:
    return ET.fromstring(render_svg(sample, kit_name="GlobalFiler"))


def _called_peaks(root: ET.Element) -> dict[str, ET.Element]:
    return {
        peak.attrib["data-allele"]: peak
        for peak in root.findall('.//svg:g[@class="called-peak"]', NS)
    }


def _coordinate_source_value(peak: object) -> str | None:
    source = getattr(peak, "coordinate_source", None)
    return getattr(source, "value", None)


class CoordinateProvenanceTests(unittest.TestCase):
    def test_positioned_peak_uses_one_semantically_correct_coordinate_field(self):
        field_names = {field.name for field in fields(PositionedPeak)}
        self.assertIn("coordinate_bp", field_names)
        self.assertNotIn("nominal_bp", field_names)
        source_field = next(
            field for field in fields(PositionedPeak) if field.name == "coordinate_source"
        )
        self.assertIs(source_field.default, MISSING)

    def test_positioning_preserves_measured_nominal_and_estimated_sources(self):
        positioned = position_sample(
            _sample(
                AlleleCall(1, "8", 100, size_bp=Decimal("350.25")),
                AlleleCall(2, "9", 90),
                AlleleCall(3, "16", 80),
            ),
            kit_name="GlobalFiler",
        )
        peaks = {peak.allele: peak for peak in positioned.peaks}

        self.assertEqual(_coordinate_source_value(peaks["8"]), "measured")
        self.assertEqual(_coordinate_source_value(peaks["9"]), "nominal")
        self.assertEqual(_coordinate_source_value(peaks["16"]), "estimated")
        self.assertEqual(getattr(peaks["8"], "coordinate_bp", None), Decimal("350.25"))
        self.assertEqual(getattr(peaks["9"], "coordinate_bp", None), Decimal("353"))
        self.assertEqual(getattr(peaks["16"], "coordinate_bp", None), Decimal("381"))

    def test_measured_size_is_not_emitted_or_described_as_nominal(self):
        root = _root(_sample(AlleleCall(1, "8", 100, size_bp=Decimal("350.25"))))
        peak = _called_peaks(root)["8"]

        self.assertEqual(root.attrib.get("data-peak-coordinate-provenance"), "measured")
        self.assertEqual(peak.attrib.get("data-coordinate-source"), "measured")
        self.assertEqual(peak.attrib.get("data-coordinate-bp"), "350.25")
        self.assertEqual(peak.attrib.get("data-measured-bp"), "350.25")
        self.assertNotIn("data-nominal-bp", peak.attrib)
        description = root.find("svg:desc", NS)
        self.assertIn("measured fragment sizes exported", description.text)
        self.assertNotIn("not measured fragment sizes", description.text)
        metadata = json.loads(root.find("svg:metadata", NS).text)
        self.assertEqual(metadata["peak_coordinate_provenance"], "measured")
        self.assertEqual(metadata["peak_coordinate_source_counts"], {"measured": 1})
        self.assertEqual(
            {element.text for element in root.findall('.//svg:text[@class="axis-unit"]', NS)},
            {"bp"},
        )

    def test_nominal_and_estimated_coordinates_have_distinct_metadata(self):
        nominal_root = _root(_sample(AlleleCall(1, "9", 100)))
        nominal = _called_peaks(nominal_root)["9"]
        self.assertEqual(nominal.attrib.get("data-coordinate-source"), "nominal")
        self.assertEqual(nominal.attrib.get("data-coordinate-bp"), "353")
        self.assertEqual(nominal.attrib.get("data-nominal-bp"), "353")
        self.assertNotIn("data-estimated-bp", nominal.attrib)

        estimated_root = _root(_sample(AlleleCall(1, "16", 100)))
        estimated = _called_peaks(estimated_root)["16"]
        self.assertEqual(estimated.attrib.get("data-coordinate-source"), "estimated")
        self.assertEqual(estimated.attrib.get("data-coordinate-bp"), "381")
        self.assertEqual(estimated.attrib.get("data-estimated-bp"), "381")
        self.assertNotIn("data-nominal-bp", estimated.attrib)
        self.assertIn("repeat-based estimate", estimated_root.find("svg:desc", NS).text)

    def test_mixed_coordinate_sources_are_reported_at_document_level(self):
        root = _root(
            _sample(
                AlleleCall(1, "8", 100, size_bp=Decimal("350.25")),
                AlleleCall(2, "9", 90),
            )
        )
        self.assertEqual(root.attrib.get("data-peak-coordinate-provenance"), "mixed")
        metadata = json.loads(root.find("svg:metadata", NS).text)
        self.assertEqual(metadata["peak_coordinate_provenance"], "mixed")
        self.assertEqual(
            metadata["peak_coordinate_source_counts"],
            {"measured": 1, "nominal": 1},
        )
        description = root.find("svg:desc", NS)
        self.assertIn("mix", description.text)
        self.assertIn("measured fragment sizes", description.text)
        self.assertIn("nominal kit display coordinates", description.text)


if __name__ == "__main__":
    unittest.main()
