from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from epg_renderer import render_batch
from epg_renderer.render_options import SvgRenderError

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "globalfiler_minimal.tsv"


class BatchOutputLifecycleTests(unittest.TestCase):
    @staticmethod
    def _invalid_sample_file(directory: Path) -> Path:
        lines = FIXTURE.read_text(encoding="utf-8").splitlines()
        fields = lines[-1].split("\t")
        fields[1] = "UNKNOWN_MARKER"
        lines[-1] = "\t".join(fields)
        path = directory / "invalid.tsv"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    @staticmethod
    def _multi_sample_file(directory: Path) -> Path:
        lines = FIXTURE.read_text(encoding="utf-8").splitlines()
        second = [line.replace("S1\t", "Sample / Two\t", 1) for line in lines[1:]]
        path = directory / "multi.tsv"
        path.write_text("\n".join(lines + second) + "\n", encoding="utf-8")
        return path

    def test_failed_sample_rerun_removes_previous_successful_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "out"
            render_batch(FIXTURE, output, kit_name="GlobalFiler")
            previous = output / "S1.svg"
            self.assertTrue(previous.is_file())

            result = render_batch(
                self._invalid_sample_file(root),
                output,
                kit_name="GlobalFiler",
                continue_on_error=True,
            )

            self.assertEqual((result.succeeded, result.failed), (0, 1))
            self.assertFalse(previous.exists())
            payload = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertIsNone(payload["items"][0]["output_file"])

    def test_parse_failure_retires_previous_outputs_but_preserves_unrelated_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "out"
            render_batch(FIXTURE, output, kit_name="GlobalFiler")
            unrelated = output / "notes.txt"
            unrelated.write_text("keep me", encoding="utf-8")
            invalid = root / "invalid.tsv"
            invalid.write_text("not a GeneMapper table\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                render_batch(invalid, output)

            self.assertFalse((output / "S1.svg").exists())
            self.assertEqual(unrelated.read_text(encoding="utf-8"), "keep me")
            payload = json.loads((output / "epg_batch_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["items"], [])
            self.assertIn("batch_error", payload)

    def test_successful_rerun_retires_outputs_for_removed_samples(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "out"
            render_batch(self._multi_sample_file(root), output, kit_name="GlobalFiler")
            removed_sample = output / "Sample___Two.svg"
            self.assertTrue(removed_sample.is_file())

            result = render_batch(FIXTURE, output, kit_name="GlobalFiler")

            self.assertEqual((result.succeeded, result.failed), (1, 0))
            self.assertTrue((output / "S1.svg").is_file())
            self.assertFalse(removed_sample.exists())

    def test_corrupt_previous_manifest_aborts_without_deleting_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out"
            render_batch(FIXTURE, output, kit_name="GlobalFiler")
            previous = output / "S1.svg"
            manifest = output / "epg_batch_manifest.json"
            manifest.write_text("{not json}\n", encoding="utf-8")

            with self.assertRaisesRegex(SvgRenderError, "previous batch manifest"):
                render_batch(FIXTURE, output, kit_name="GlobalFiler")

            self.assertTrue(previous.is_file())
            self.assertEqual(manifest.read_text(encoding="utf-8"), "{not json}\n")

    def test_malformed_manifest_structures_are_rejected_before_rendering(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out"
            output.mkdir()
            accepted_payloads = []
            invalid_payloads = (
                [],
                {"items": "not an array"},
                {"items": ["not an object"]},
                {"items": [{"output_file": 42}]},
            )

            for payload in invalid_payloads:
                (output / "epg_batch_manifest.json").write_text(
                    json.dumps(payload), encoding="utf-8"
                )
                try:
                    render_batch(FIXTURE, output, kit_name="GlobalFiler")
                except SvgRenderError as exc:
                    self.assertIn("previous batch manifest", str(exc))
                else:
                    accepted_payloads.append(payload)
                (output / "S1.svg").unlink(missing_ok=True)

            self.assertEqual(accepted_payloads, [])

    def test_failed_manifest_items_without_output_files_are_safe_to_reuse(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out"
            output.mkdir()
            manifest = {
                "epg_renderer_version": "0.13.29",
                "items": [{"status": "error", "output_file": None}],
            }
            (output / "epg_batch_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

            result = render_batch(FIXTURE, output, kit_name="GlobalFiler")

            self.assertEqual((result.succeeded, result.failed), (1, 0))
            self.assertTrue((output / "S1.svg").is_file())

    def test_rerun_aborts_if_a_previous_output_cannot_be_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out"
            render_batch(FIXTURE, output, kit_name="GlobalFiler")

            with (
                mock.patch.object(Path, "unlink", side_effect=PermissionError("locked")),
                self.assertRaisesRegex(SvgRenderError, "Could not retire previous batch output"),
            ):
                render_batch(FIXTURE, output, kit_name="GlobalFiler")

            self.assertTrue((output / "S1.svg").is_file())

    def test_previous_manifest_rejects_cross_platform_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "out"
            output.mkdir()
            outside = root / "outside.svg"
            outside.write_text("unrelated", encoding="utf-8")
            accepted_names = []

            for unsafe_name in (
                "../outside.svg",
                r"..\outside.svg",
                "/tmp/outside.svg",
                r"C:\outside.svg",
                "nested/output.svg",
                r"nested\output.svg",
            ):
                manifest = {
                    "epg_renderer_version": "0.13.29",
                    "items": [{"output_file": unsafe_name}],
                }
                (output / "epg_batch_manifest.json").write_text(
                    json.dumps(manifest), encoding="utf-8"
                )
                try:
                    render_batch(FIXTURE, output, kit_name="GlobalFiler")
                except SvgRenderError as exc:
                    self.assertIn("unsafe output filename", str(exc))
                else:
                    accepted_names.append(unsafe_name)
                (output / "S1.svg").unlink(missing_ok=True)

            self.assertEqual(accepted_names, [])
            self.assertEqual(outside.read_text(encoding="utf-8"), "unrelated")


if __name__ == "__main__":
    unittest.main()
