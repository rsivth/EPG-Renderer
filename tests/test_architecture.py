from __future__ import annotations

import ast
import importlib
import inspect
import json
import unittest
import xml.etree.ElementTree as ET
from dataclasses import fields
from pathlib import Path
from unittest import mock

import epg_renderer.kit_registry as registry_module
import epg_renderer.kit_schema as schema_module
import epg_renderer.positions as positions_module
import epg_renderer.render_layout as layout_module
from epg_renderer import (
    load_kit,
    render_svg,
)
from epg_renderer.kit_schema import KitSchemaError, profile_from_payload
from epg_renderer.positions import PeakCoordinateSource, PositionedPeak, PositionedSample
from epg_renderer.render_options import (
    SvgRenderOptions,
    UnpositionedPolicy,
)

svg_module = importlib.import_module("epg_renderer.render_svg")

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).with_name("fixtures") / "globalfiler_minimal.tsv"


class ModuleBoundaryTests(unittest.TestCase):
    def test_channel_renderer_uses_one_context_object(self):
        parameters = inspect.signature(svg_module._render_channel).parameters
        self.assertEqual(tuple(parameters), ("context",))
        self.assertEqual(
            tuple(field.name for field in fields(svg_module._ChannelRenderContext)),
            (
                "root",
                "channel",
                "channel_y",
                "plan",
                "options",
                "plot_width",
                "x_min",
                "x_max",
                "max_rfu",
                "peaks",
                "marker_definitions",
                "marker_annotation_counts",
                "color",
            ),
        )

    def test_dead_collision_state_was_removed_from_label_placement(self):
        self.assertEqual(
            tuple(field.name for field in fields(layout_module.LabelPlacement)),
            ("x", "lane", "width"),
        )

    def test_registry_loader_and_schema_parser_are_separate(self):
        self.assertIs(registry_module.profile_from_payload, schema_module.profile_from_payload)
        self.assertIs(registry_module.KitProfile, schema_module.KitProfile)
        source = inspect.getsource(registry_module)
        self.assertNotIn("def _coordinate_from_payload(", source)
        self.assertNotIn("def _require_exact_keys(", source)
        self.assertLess(len(source.splitlines()), 190)

    def test_coordinate_model_module_does_not_depend_on_kit_registry(self):
        tree = ast.parse(inspect.getsource(positions_module))
        registry_imports = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and node.level == 1
            and node.module == "kit_registry"
        ]
        self.assertEqual(registry_imports, [])

    def test_coordinate_model_operations_do_not_consult_global_registry(self):
        model = load_kit("GlobalFiler").coordinate_model
        with mock.patch.object(
            registry_module,
            "get_kit",
            side_effect=AssertionError("coordinate model consulted the global registry"),
        ):
            self.assertIs(model.marker("AM"), model.marker("Amelogenin"))
            model.validate()


class ArchitectureBehaviourTests(unittest.TestCase):
    def test_one_omitted_peak_is_counted_once(self):
        profile = load_kit("GlobalFiler")
        marker = profile.coordinate_model.markers[0]
        positioned = PositionedSample(
            sample_id="S",
            kit_name=profile.kit.name,
            coordinate_model_version=profile.coordinate_model.model_version,
            coordinate_kind=profile.coordinate_model.coordinate_kind,
            exact_bin_centres=profile.coordinate_model.exact_bin_centres,
            peaks=(
                PositionedPeak(
                    marker=marker.marker,
                    dye=marker.dye,
                    source_dye=marker.dye,
                    allele_index=1,
                    allele=marker.coordinates[0].allele,
                    height=100,
                    coordinate_bp=None,
                    marker_range_min_bp=marker.range_min_bp,
                    marker_range_max_bp=marker.range_max_bp,
                    coordinate_source=PeakCoordinateSource.UNPOSITIONED,
                ),
            ),
            issues=(),
        )
        svg = render_svg(
            positioned, options=SvgRenderOptions(unpositioned_policy=UnpositionedPolicy.OMIT)
        )
        root = ET.fromstring(svg)
        namespace = {"svg": "http://www.w3.org/2000/svg"}
        metadata = json.loads(root.find("svg:metadata", namespace).text)
        self.assertEqual(metadata["omitted_unpositioned_peaks"], 1)
        warning = root.find("svg:text[@data-omitted-unpositioned-peaks]", namespace)
        self.assertEqual(warning.attrib["data-omitted-unpositioned-peaks"], "1")

    def test_all_registry_profiles_still_load_after_schema_extraction(self):
        names = registry_module.available_kit_names()
        self.assertEqual(len(names), 14)
        for name in names:
            with self.subTest(kit=name):
                profile = registry_module.get_kit_profile(name)
                profile.coordinate_model.validate(profile.kit)

    def test_schema_rejects_canonical_duplicate_explicit_positions(self):
        payload = json.loads(
            (ROOT / "src" / "epg_renderer" / "data" / "kits" / "globalfiler_v1.json").read_text(
                encoding="utf-8"
            )
        )
        marker = next(
            item
            for item in payload["markers"]
            if item["coordinate"]["placement_method"] == "explicit"
        )
        marker["coordinate"]["explicit_positions"]["01"] = marker["coordinate"][
            "explicit_positions"
        ]["1"]
        with self.assertRaisesRegex(KitSchemaError, "duplicate canonical allele"):
            profile_from_payload(payload)

    def test_schema_rejects_duplicate_canonical_linkage_markers(self):
        payload = json.loads(
            (
                ROOT / "src" / "epg_renderer" / "data" / "kits" / "investigator_argus_x12_v1.json"
            ).read_text(encoding="utf-8")
        )
        group = payload["kit"]["linkage_groups"]["Linkage group 1"]
        group.append(group[0].lower())
        with self.assertRaisesRegex(KitSchemaError, "duplicate canonical marker"):
            profile_from_payload(payload)

    def test_schema_rejects_blank_optional_marker_group(self):
        payload = json.loads(
            (
                ROOT / "src" / "epg_renderer" / "data" / "kits" / "investigator_argus_x12_v1.json"
            ).read_text(encoding="utf-8")
        )
        payload["markers"][0]["copy_group"] = "   "
        with self.assertRaisesRegex(KitSchemaError, "non-empty string or null"):
            profile_from_payload(payload)


if __name__ == "__main__":
    unittest.main()
