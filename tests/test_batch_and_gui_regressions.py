from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from epg_renderer import (
    list_kits,
    load_kit,
    load_project,
    render_batch,
    render_file,
)
from epg_renderer.gui_workflow import (
    choose_output_path_value,
    inspect_genemapper_file,
    suggested_output_path,
    validated_output_path,
)
from epg_renderer.kit_workflow import KitResolutionError, resolve_kit
from epg_renderer.models import AlleleCall, MarkerCall, SampleCall
from epg_renderer.parser import DuplicateMarkerError, GeneMapperParserError

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "globalfiler_minimal.tsv"


class CanonicalDuplicateMarkerTests(unittest.TestCase):
    def test_parser_rejects_case_only_duplicate_marker_rows(self):
        text = "Sample Name\tMarker\tDye\tAllele 1\tHeight 1\nS\tD3S1358\tFAM\t15\t100\nS\td3s1358\tFAM\t16\t90\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.tsv"
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(DuplicateMarkerError) as caught:
                load_project(path)
        self.assertIn("D3S1358", str(caught.exception))
        self.assertIn("d3s1358", str(caught.exception))

    def test_kit_resolution_rejects_alias_duplicate_marker_rows(self):
        sample = SampleCall(
            "S",
            {
                "AM": MarkerCall("AM", "VIC", (AlleleCall(1, "X", 100),)),
                "Amelogenin": MarkerCall("Amelogenin", "VIC", (AlleleCall(1, "Y", 90),)),
            },
        )
        with self.assertRaises(KitResolutionError) as caught:
            resolve_kit(sample, kit_name="GlobalFiler")
        message = str(caught.exception)
        self.assertIn("AM", message)
        self.assertIn("Amelogenin", message)


class BatchRecoveryTests(unittest.TestCase):
    @staticmethod
    def _partly_invalid_file(directory: Path) -> Path:
        lines = FIXTURE.read_text(encoding="utf-8").splitlines()
        valid_rows = lines[1:]
        invalid_rows = []
        for line in valid_rows:
            fields = line.split("\t")
            fields[0] = "Invalid"
            if fields[1] == "D2S1338":
                fields[1] = "UNKNOWN_MARKER"
            invalid_rows.append("\t".join(fields))
        path = directory / "mixed.tsv"
        path.write_text(
            lines[0] + "\n" + "\n".join(valid_rows + invalid_rows) + "\n", encoding="utf-8"
        )
        return path

    def test_continue_on_error_renders_valid_sample_and_writes_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = render_batch(
                self._partly_invalid_file(root),
                root / "out",
                kit_name="GlobalFiler",
                continue_on_error=True,
            )
            self.assertEqual(result.succeeded, 1)
            self.assertEqual(result.failed, 1)
            self.assertTrue((root / "out" / "S1.svg").is_file())
            self.assertTrue(result.manifest_path.is_file())
            payload = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["succeeded"], 1)
            self.assertEqual(payload["failed"], 1)
            self.assertEqual([item["sample_id"] for item in payload["items"]], ["S1", "Invalid"])
            self.assertIn("UNKNOWN_MARKER", payload["items"][1]["error"])

    def test_fail_fast_writes_partial_manifest_before_reraising(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "out"
            with self.assertRaises(KitResolutionError):
                render_batch(
                    self._partly_invalid_file(root),
                    output,
                    kit_name="GlobalFiler",
                    continue_on_error=False,
                )
            manifest = output / "epg_batch_manifest.json"
            self.assertTrue(manifest.is_file())
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(payload["succeeded"], 1)
            self.assertEqual(payload["failed"], 1)
            self.assertEqual(payload["items"][-1]["sample_id"], "Invalid")

    def test_parse_failure_writes_batch_manifest_before_reraising(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            invalid = root / "invalid.tsv"
            invalid.write_text("not a GeneMapper table\n", encoding="utf-8")
            output = root / "out"
            with self.assertRaises(GeneMapperParserError):
                render_batch(invalid, output)
            payload = json.loads((output / "epg_batch_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["items"], [])
            self.assertIn("GeneMapper", payload["batch_error"])

    def test_unknown_explicit_kit_writes_manifest_before_reraising(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out"
            with self.assertRaises(KitResolutionError):
                render_batch(FIXTURE, output, kit_name="Not a kit")
            payload = json.loads((output / "epg_batch_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["kit_name"], "Not a kit")
            self.assertIn("Unknown kit", payload["batch_error"])

    def test_unexpected_batch_error_is_not_swallowed_and_manifest_is_written(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "out"
            with (
                mock.patch(
                    "epg_renderer.batch.write_epg_output",
                    side_effect=RuntimeError("programming defect"),
                ),
                self.assertRaisesRegex(RuntimeError, "programming defect"),
            ):
                render_batch(FIXTURE, output, kit_name="GlobalFiler", continue_on_error=True)
            payload = json.loads((output / "epg_batch_manifest.json").read_text(encoding="utf-8"))
            self.assertIn("Unexpected RuntimeError", payload["items"][0]["error"])
            self.assertIn("RuntimeError", payload["batch_error"])


class GuiKitSelectionTests(unittest.TestCase):
    def test_gui_only_reports_kits_that_explicit_resolution_accepts(self):
        lines = FIXTURE.read_text(encoding="utf-8").splitlines()
        fields = lines[-1].split("\t")
        fields[1] = "UNKNOWN_MARKER"
        lines[-1] = "\t".join(fields)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unknown.tsv"
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            inspection = inspect_genemapper_file(path)
            decision = inspection.sample("S1")
            sample = inspection.project.sample("S1")
        for name in decision.compatible_kit_names:
            with self.subTest(kit=name):
                resolve_kit(sample, kit_name=name, require_genemapper_compatible=True)
        self.assertNotIn("GlobalFiler", decision.compatible_kit_names)

    def test_powerplex_35gy_is_not_offered_for_genemapper_workflows(self):
        profile = load_kit("PowerPlex 35GY")
        markers = {
            marker.name: MarkerCall(
                marker.name,
                marker.dye,
                (AlleleCall(1, marker.ladder_alleles[0], 100 + index),),
            )
            for index, marker in enumerate(profile.kit.markers)
        }
        sample = SampleCall("S", markers)
        with self.assertRaises(KitResolutionError):
            resolve_kit(sample, kit_name="PowerPlex 35GY", require_genemapper_compatible=True)

    def test_gui_kit_name_list_excludes_unverified_exports(self):
        self.assertNotIn(
            "PowerPlex 35GY", tuple(profile.kit.name for profile in list_kits(genemapper_only=True))
        )
        self.assertIn(
            "GlobalFiler", tuple(profile.kit.name for profile in list_kits(genemapper_only=True))
        )

    def test_explicit_35gy_gene_mapper_render_is_rejected(self):
        profile = load_kit("PowerPlex 35GY")
        header = "Sample Name\tMarker\tDye\tAllele 1\tHeight 1\n"
        rows = [
            f"S\t{marker.name}\t{marker.dye}\t{marker.ladder_alleles[0]}\t100"
            for marker in profile.kit.markers
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "35gy.tsv"
            input_path.write_text(header + "\n".join(rows) + "\n", encoding="utf-8")
            with self.assertRaises(KitResolutionError) as caught:
                render_file(input_path, root / "out.svg", kit_name="PowerPlex 35GY")
        self.assertIn("GeneMapper", str(caught.exception))


class OutputPathTests(unittest.TestCase):
    def test_suggestion_tracks_selected_sample(self):
        source = Path("/case/run.tsv")
        first = suggested_output_path(source, "Sample A", "svg")
        second = suggested_output_path(source, "Sample B", "svg")
        self.assertEqual(first.name, "Sample_A_epg.svg")
        self.assertEqual(second.name, "Sample_B_epg.svg")
        self.assertNotEqual(first, second)

    def test_automatic_suggestion_updates_but_manual_path_is_preserved(self):
        old = "/case/Sample_A_epg.svg"
        new = "/case/Sample_B_epg.svg"
        self.assertEqual(choose_output_path_value(old, old, new), new)
        self.assertEqual(
            choose_output_path_value("/custom/result.svg", old, new), "/custom/result.svg"
        )

    def test_blank_output_path_is_rejected(self):
        with self.assertRaises(ValueError):
            validated_output_path("   ", "svg")


if __name__ == "__main__":
    unittest.main()
