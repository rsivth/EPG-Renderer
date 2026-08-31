from __future__ import annotations

import json
import unittest
from importlib.resources import files

from epg_renderer import (
    list_kits,
    load_kit,
)
from epg_renderer.kit_registry import clear_registry_cache
from epg_renderer.kit_schema import KitSchemaError, profile_from_payload


def _payload(name: str) -> dict:
    resource = files("epg_renderer").joinpath(f"data/kits/{name}")
    with resource.open("r", encoding="utf-8") as handle:
        return json.load(handle)


class JsonKitRegistryTests(unittest.TestCase):
    def test_profiles_are_cached_and_aliases_share_identity(self):
        self.assertIs(load_kit("GFI"), load_kit("GlobalFiler"))
        self.assertIs(load_kit("AmpFlSTR NGM"), load_kit("NGM"))

    def test_registry_cache_can_be_cleared_safely(self):
        first = load_kit("NGM")
        clear_registry_cache()
        second = load_kit("NGM")
        self.assertIsNot(first, second)
        self.assertEqual(first.kit, second.kit)

    def test_unknown_kit_lists_available_names(self):
        with self.assertRaisesRegex(KeyError, "Available kits"):
            load_kit("unknown")

    def test_registered_kit_accessor(self):
        self.assertEqual(load_kit("NGM").kit.name, "NGM")

    def test_registered_coordinate_accessor(self):
        model = load_kit("NGM").coordinate_model
        self.assertEqual(model.kit_name, "NGM")
        self.assertEqual(model.model_version, "0.4-ngm1")

    def test_formal_schema_resource_is_packaged(self):
        resource = files("epg_renderer").joinpath("data/kit_definition_schema.json")
        with resource.open("r", encoding="utf-8") as handle:
            schema = json.load(handle)
        self.assertEqual(schema["properties"]["schema_version"]["const"], "1.1")
        self.assertEqual(schema["type"], "object")

    def test_every_profile_validates(self):
        for profile in list_kits():
            with self.subTest(kit=profile.kit.name):
                profile.coordinate_model.validate(profile.kit)

    def test_every_coordinate_model_uses_current_schema(self):
        for profile in list_kits():
            with self.subTest(kit=profile.kit.name):
                self.assertEqual(profile.coordinate_model.schema_version, "1.1")

    def test_globalfiler_json_contains_no_code_specific_marker_exception(self):
        payload = _payload("globalfiler_v1.json")
        marker_names = [marker["name"] for marker in payload["markers"]]
        self.assertIn("TPOX", marker_names)
        tpox = next(marker for marker in payload["markers"] if marker["name"] == "TPOX")
        self.assertEqual(tpox["coordinate"]["placement_method"], "anchored_repeat")

    def test_dye_aliases_are_kit_specific(self):
        self.assertEqual(load_kit("GlobalFiler").normalize_dye("red"), "TAZ")
        self.assertEqual(load_kit("NGM").normalize_dye("red"), "PET")

    def test_root_unknown_field_is_rejected(self):
        payload = _payload("ngm_v1.json")
        payload["unexpected"] = True
        with self.assertRaises(KitSchemaError):
            profile_from_payload(payload)

    def test_missing_required_root_field_is_rejected(self):
        payload = _payload("ngm_v1.json")
        del payload["sources"]
        with self.assertRaises(KitSchemaError):
            profile_from_payload(payload)

    def test_duplicate_channel_code_is_rejected(self):
        payload = _payload("ngm_v1.json")
        payload["kit"]["channels"][1]["code"] = "FAM"
        with self.assertRaises(KitSchemaError):
            profile_from_payload(payload)

    def test_noncontiguous_channel_order_is_rejected(self):
        payload = _payload("ngm_v1.json")
        payload["kit"]["channels"][3]["order"] = 8
        with self.assertRaises(KitSchemaError):
            profile_from_payload(payload)

    def test_invalid_svg_color_is_rejected(self):
        payload = _payload("ngm_v1.json")
        payload["kit"]["channels"][0]["svg_color"] = "blue"
        with self.assertRaises(KitSchemaError):
            profile_from_payload(payload)

    def test_marker_with_unknown_dye_is_rejected(self):
        payload = _payload("ngm_v1.json")
        payload["markers"][0]["dye"] = "UNKNOWN"
        with self.assertRaises(KitSchemaError):
            profile_from_payload(payload)

    def test_duplicate_marker_is_rejected(self):
        payload = _payload("ngm_v1.json")
        payload["markers"][1]["name"] = payload["markers"][0]["name"]
        with self.assertRaises(KitSchemaError):
            profile_from_payload(payload)

    def test_duplicate_ladder_allele_is_rejected(self):
        payload = _payload("ngm_v1.json")
        payload["markers"][0]["ladder_alleles"].append("8")
        with self.assertRaises(KitSchemaError):
            profile_from_payload(payload)

    def test_invalid_marker_range_is_rejected(self):
        payload = _payload("ngm_v1.json")
        payload["markers"][0]["coordinate"]["range_max_bp"] = 10
        with self.assertRaises(KitSchemaError):
            profile_from_payload(payload)

    def test_explicit_positions_must_match_ladder(self):
        payload = _payload("ngm_v1.json")
        amel = next(marker for marker in payload["markers"] if marker["name"] == "Amelogenin")
        del amel["coordinate"]["explicit_positions"]["Y"]
        with self.assertRaises(KitSchemaError):
            profile_from_payload(payload)

    def test_coordinate_quality_flag_must_be_consistent(self):
        payload = _payload("ngm_v1.json")
        payload["coordinate_model"]["exact_bin_centres"] = True
        with self.assertRaises(KitSchemaError):
            profile_from_payload(payload)

    def test_empty_source_list_is_rejected(self):
        payload = _payload("ngm_v1.json")
        payload["sources"] = []
        with self.assertRaises(KitSchemaError):
            profile_from_payload(payload)

    def test_marker_alias_collision_is_rejected(self):
        payload = _payload("ngm_v1.json")
        payload["markers"][1]["aliases"] = [payload["markers"][0]["name"]]
        with self.assertRaises(KitSchemaError):
            profile_from_payload(payload)

    def test_marker_json_order_must_match_channel_order(self):
        payload = _payload("ngm_v1.json")
        payload["markers"][0], payload["markers"][1] = (
            payload["markers"][1],
            payload["markers"][0],
        )
        with self.assertRaises(KitSchemaError):
            profile_from_payload(payload)


if __name__ == "__main__":
    unittest.main()
