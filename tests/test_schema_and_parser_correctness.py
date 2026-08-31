from __future__ import annotations

import copy
import csv
import json
import tempfile
import unittest
from pathlib import Path

from epg_renderer import (
    load_kit,
    load_project,
)
from epg_renderer.kit_schema import KitSchemaError, profile_from_payload
from epg_renderer.parser import DuplicateHeaderError, GeneMapperParserError
from epg_renderer.positions import CoordinateKind

ROOT = Path(__file__).resolve().parents[1]
KIT_DIR = ROOT / "src" / "epg_renderer" / "data" / "kits"


def _payload(filename: str) -> dict[str, object]:
    return json.loads((KIT_DIR / filename).read_text(encoding="utf-8"))


def _write(directory: str, name: str, content: str) -> Path:
    path = Path(directory) / name
    path.write_text(content, encoding="utf-8", newline="")
    return path


class ParserCorrectnessTests(unittest.TestCase):
    def test_quoted_multiline_field_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = _write(
                directory,
                "multiline.csv",
                'Sample Name,Marker,Dye,Allele 1,Height 1\r\n"S1\r\ncontinued",D3S1358,B,15,100\r\n',
            )
            project = load_project(path, delimiter=",")
        self.assertEqual(tuple(project.samples), ("S1\r\ncontinued",))

    def test_semantically_duplicate_indexed_columns_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = _write(
                directory,
                "duplicates.tsv",
                "Sample Name\tMarker\tDye\tAllele 1\tAllele  1\tHeight 1\nS1\tD3S1358\tB\t15\t16\t100\n",
            )
            with self.assertRaisesRegex(
                DuplicateHeaderError, "semantic indexed column.*Allele 1.*Allele  1"
            ):
                load_project(path, delimiter="\t")

    def test_valid_escaped_quote_blank_row_and_quoted_final_field(self):
        with tempfile.TemporaryDirectory() as directory:
            path = _write(
                directory,
                "quoted.csv",
                'Sample Name,Marker,Dye,Allele 1,Height 1\r\n\r\n"S""1",D3S1358,B,15,"100"\r\n',
            )
            project = load_project(path, delimiter=",")
        self.assertEqual(tuple(project.samples), ('S"1',))

    def test_csv_reader_errors_are_wrapped_with_line_number(self):
        previous_limit = csv.field_size_limit()
        try:
            csv.field_size_limit(8)
            with tempfile.TemporaryDirectory() as directory:
                path = _write(
                    directory,
                    "oversized.csv",
                    "Sample Name,Marker,Dye,Allele 1,Height 1\nS1,D3S1358,B,15,100\n",
                )
                with self.assertRaisesRegex(GeneMapperParserError, "Invalid CSV syntax.*line 1"):
                    load_project(path, delimiter=",")
        finally:
            csv.field_size_limit(previous_limit)

    def test_explicit_utf8_bom_only_header_is_rejected_as_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bom.csv"
            path.write_bytes(b"\xef\xbb\xbf")
            with self.assertRaisesRegex(GeneMapperParserError, "Header row is empty"):
                load_project(path, delimiter=",", encoding="utf-8")

    def test_unknown_encoding_name_is_wrapped(self):
        with tempfile.TemporaryDirectory() as directory:
            path = _write(directory, "input.tsv", "content")
            with self.assertRaisesRegex(
                GeneMapperParserError, "Unknown text encoding.*not-a-codec"
            ):
                load_project(path, encoding="not-a-codec")

    def test_unclosed_quoted_field_is_reported_as_csv_syntax_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = _write(
                directory,
                "broken.csv",
                'Sample Name,Marker,Dye,Allele 1,Height 1\n"S1,D3S1358,B,15,100\n',
            )
            with self.assertRaisesRegex(GeneMapperParserError, "Invalid CSV syntax.*line 2"):
                load_project(path, delimiter=",")

    def test_quote_inside_unquoted_field_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = _write(
                directory,
                "stray-quote.csv",
                'Sample Name,Marker,Dye,Allele 1,Height 1\nS"1,D3S1358,B,15,100\n',
            )
            with self.assertRaisesRegex(GeneMapperParserError, "Invalid CSV syntax.*line 2"):
                load_project(path, delimiter=",")


class CoordinateSchemaTests(unittest.TestCase):
    def test_exact_bin_claim_rejects_any_derived_marker_coordinates(self):
        payload = _payload("globalfiler_v1.json")
        coordinate_model = payload["coordinate_model"]
        assert isinstance(coordinate_model, dict)
        coordinate_model["coordinate_kind"] = "exact_bin_centres"
        coordinate_model["exact_bin_centres"] = True
        with self.assertRaisesRegex(KitSchemaError, "exact bin centres.*explicit coordinates"):
            profile_from_payload(payload)

    def test_fully_explicit_model_may_claim_exact_bin_centres(self):
        payload = _payload("globalfiler_v1.json")
        profile = load_kit("GlobalFiler")
        coordinate_by_marker = {
            definition.marker: definition.coordinate_map()
            for definition in profile.coordinate_model.markers
        }
        markers = payload["markers"]
        assert isinstance(markers, list)
        for raw_marker in markers:
            assert isinstance(raw_marker, dict)
            marker_name = raw_marker["name"]
            coordinate = raw_marker["coordinate"]
            assert isinstance(marker_name, str)
            assert isinstance(coordinate, dict)
            coordinate.clear()
            coordinate.update(
                {
                    "range_min_bp": float(
                        profile.coordinate_model.marker(marker_name).range_min_bp
                    ),
                    "range_max_bp": float(
                        profile.coordinate_model.marker(marker_name).range_max_bp
                    ),
                    "placement_method": "explicit",
                    "explicit_positions": {
                        allele: float(position)
                        for allele, position in coordinate_by_marker[marker_name].items()
                    },
                    "source_note": "Verified explicit allelic-ladder bin centres.",
                }
            )
        coordinate_model = payload["coordinate_model"]
        assert isinstance(coordinate_model, dict)
        coordinate_model["coordinate_kind"] = "exact_bin_centres"
        coordinate_model["exact_bin_centres"] = True
        parsed = profile_from_payload(payload)
        self.assertIs(parsed.coordinate_model.coordinate_kind, CoordinateKind.EXACT_BIN_CENTRES)
        self.assertTrue(parsed.coordinate_model.exact_bin_centres)

    def test_json_schemas_define_disjoint_coordinate_variants(self):
        for filename in ("kit_definition_schema.json",):
            with self.subTest(schema=filename):
                schema = json.loads(
                    (ROOT / "src" / "epg_renderer" / "data" / filename).read_text(encoding="utf-8")
                )
                coordinate = schema["properties"]["markers"]["items"]["properties"]["coordinate"]
                variants = coordinate["oneOf"]
                self.assertEqual(len(variants), 3)
                self.assertTrue(all(item["additionalProperties"] is False for item in variants))
                methods = {item["properties"]["placement_method"]["const"] for item in variants}
                self.assertEqual(methods, {"range_centered_repeat", "anchored_repeat", "explicit"})

    def test_coordinate_methods_reject_fields_from_other_variants(self):
        cases = (
            ("globalfiler_v1.json", "range_centered_repeat", "explicit_positions", {"1": 100}),
            ("globalfiler_v1.json", "explicit", "repeat_length_bp", 4),
            ("globalfiler_v1.json", "anchored_repeat", "explicit_positions", {"1": 100}),
        )
        for filename, method, field, value in cases:
            with self.subTest(method=method, field=field):
                payload = _payload(filename)
                markers = payload["markers"]
                assert isinstance(markers, list)
                marker = next(
                    item
                    for item in markers
                    if isinstance(item, dict)
                    and isinstance(item.get("coordinate"), dict)
                    and (item["coordinate"].get("placement_method") == method)
                )
                coordinate = marker["coordinate"]
                assert isinstance(coordinate, dict)
                coordinate[field] = value
                with self.assertRaisesRegex(KitSchemaError, f"placement method {method!r}.*field"):
                    profile_from_payload(payload)


class MetadataConsistencyTests(unittest.TestCase):
    def test_control_flag_must_match_marker_type_in_both_directions(self):
        payload = _payload("investigator_argus_x12_v1.json")
        markers = payload["markers"]
        assert isinstance(markers, list)
        for marker_type, is_control in (("str", True), ("control", False)):
            with self.subTest(marker_type=marker_type, is_control=is_control):
                changed = copy.deepcopy(payload)
                changed_markers = changed["markers"]
                assert isinstance(changed_markers, list)
                marker = changed_markers[0]
                assert isinstance(marker, dict)
                marker["marker_type"] = marker_type
                marker["is_control"] = is_control
                with self.assertRaisesRegex(
                    KitSchemaError, "marker_type.*is_control.*inconsistent"
                ):
                    profile_from_payload(changed)

    def test_marker_linkage_group_must_exist(self):
        payload = _payload("investigator_argus_x12_v1.json")
        markers = payload["markers"]
        assert isinstance(markers, list)
        marker = markers[1]
        assert isinstance(marker, dict)
        marker["linkage_group"] = "Unknown group"
        with self.assertRaisesRegex(KitSchemaError, "references unknown linkage group"):
            profile_from_payload(payload)

    def test_marker_must_be_listed_in_its_declared_linkage_group(self):
        payload = _payload("investigator_argus_x12_v1.json")
        markers = payload["markers"]
        assert isinstance(markers, list)
        marker = next(
            item for item in markers if isinstance(item, dict) and item["linkage_group"] is not None
        )
        marker_name = marker["name"]
        group_name = marker["linkage_group"]
        kit = payload["kit"]
        assert isinstance(kit, dict)
        groups = kit["linkage_groups"]
        assert isinstance(groups, dict)
        group = groups[group_name]
        assert isinstance(group, list)
        group.remove(marker_name)
        with self.assertRaisesRegex(KitSchemaError, "is not listed in declared linkage group"):
            profile_from_payload(payload)

    def test_linkage_group_member_must_declare_the_same_group(self):
        payload = _payload("investigator_argus_x12_v1.json")
        kit = payload["kit"]
        markers = payload["markers"]
        assert isinstance(kit, dict)
        assert isinstance(markers, list)
        groups = kit["linkage_groups"]
        assert isinstance(groups, dict)
        group_name, group_markers = next(iter(groups.items()))
        assert isinstance(group_markers, list)
        marker_name = group_markers[0]
        marker = next(
            item for item in markers if isinstance(item, dict) and item["name"] == marker_name
        )
        marker["linkage_group"] = None
        with self.assertRaisesRegex(KitSchemaError, "lists marker.*does not declare that group"):
            profile_from_payload(payload)


class IdentifierValidationTests(unittest.TestCase):
    def test_lookup_names_and_aliases_cannot_normalize_to_empty(self):
        cases = (
            ("kit name", lambda payload: payload["kit"].__setitem__("name", "---")),
            ("kit alias", lambda payload: payload["kit"]["aliases"].append("___")),
            (
                "channel code",
                lambda payload: payload["kit"]["channels"][0].__setitem__("code", "---"),
            ),
            ("dye alias", lambda payload: payload["kit"]["channels"][0]["aliases"].append("___")),
            ("marker name", lambda payload: payload["markers"][0].__setitem__("name", "---")),
            ("marker alias", lambda payload: payload["markers"][0]["aliases"].append("___")),
        )
        for label, mutate in cases:
            with self.subTest(label=label):
                payload = _payload("identifiler_v1.json")
                mutate(payload)
                with self.assertRaisesRegex(KitSchemaError, "normalizes to an empty identifier"):
                    profile_from_payload(payload)


if __name__ == "__main__":
    unittest.main()
