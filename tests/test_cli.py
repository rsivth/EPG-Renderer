from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from importlib.util import find_spec
from pathlib import Path

RASTER_DEPENDENCIES_AVAILABLE = find_spec("cairosvg") is not None and find_spec("PIL") is not None

ROOT = Path(__file__).resolve().parents[1]


class CommandLineTests(unittest.TestCase):
    def _run(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "epg_renderer", *arguments],
            cwd=ROOT,
            env={**__import__("os").environ, "PYTHONPATH": str(ROOT / "src")},
            capture_output=True,
            text=True,
            check=False,
        )

    def test_cli_help_lists_supported_suffixes(self):
        result = self._run("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(".svg", result.stdout)
        self.assertIn(".png", result.stdout)
        self.assertIn(".jpg", result.stdout)
        self.assertIn("--list-kits", result.stdout)

    def test_cli_lists_every_bundled_kit_without_positional_arguments(self):
        result = self._run("--list-kits")
        self.assertEqual(result.returncode, 0, result.stderr)
        names = tuple(line for line in result.stdout.splitlines() if line)
        self.assertEqual(len(names), 14)
        self.assertEqual(names[0], "GlobalFiler")
        self.assertIn("PowerPlex 35GY", names)
        self.assertEqual(names[-1], "Yfiler Plus")

    def test_cli_missing_input_is_concise(self):
        result = self._run("missing.tsv", "out.svg")
        self.assertEqual(result.returncode, 2)
        self.assertIn("epg-render: error:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_cli_creates_svg(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "out.svg"
            result = self._run(
                str(ROOT / "tests/fixtures/globalfiler_minimal.tsv"),
                str(target),
                "--kit",
                "GlobalFiler",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(target.is_file())
            self.assertIn(str(target.resolve()), result.stdout)

    @unittest.skipUnless(RASTER_DEPENDENCIES_AVAILABLE, "Raster dependencies are not installed")
    def test_cli_creates_jpeg(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "out.jpg"
            result = self._run(
                str(ROOT / "tests/fixtures/globalfiler_minimal.tsv"),
                str(target),
                "--kit",
                "GlobalFiler",
                "--raster-scale",
                "0.25",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            with Image.open(target) as image:
                self.assertEqual(image.format, "JPEG")


if __name__ == "__main__":
    unittest.main()


class CommandDispatchTests(unittest.TestCase):
    def test_main_dispatches_single_sample_without_subprocess(self):
        from types import SimpleNamespace
        from unittest import mock

        from epg_renderer import cli

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out.svg"
            report = SimpleNamespace(
                messages=lambda: (),
                has_omitted_peaks=False,
                output_path=output,
            )
            with mock.patch.object(
                cli, "render_genemapper_epg_report", return_value=report
            ) as render:
                status = cli.main(["input.tsv", str(output), "--kit", "GlobalFiler"])
        self.assertEqual(status, 0)
        render.assert_called_once()

    def test_main_dispatches_successful_batch(self):
        from types import SimpleNamespace
        from unittest import mock

        from epg_renderer import cli

        result = SimpleNamespace(
            output_dir=Path("out"),
            succeeded=2,
            failed=0,
            manifest_path=Path("out/epg_batch_manifest.json"),
            warnings=(),
            items=(),
            has_omitted_peaks=False,
        )
        with mock.patch.object(cli, "render_genemapper_batch", return_value=result):
            status = cli.main(["input.tsv", "out", "--all-samples", "--format", "jpg"])
        self.assertEqual(status, 0)

    def test_main_returns_two_for_partial_batch(self):
        from types import SimpleNamespace
        from unittest import mock

        from epg_renderer import cli

        result = SimpleNamespace(
            output_dir=Path("out"),
            succeeded=1,
            failed=1,
            manifest_path=Path("out/epg_batch_manifest.json"),
            warnings=(),
            items=(),
            has_omitted_peaks=False,
        )
        with mock.patch.object(cli, "render_genemapper_batch", return_value=result):
            status = cli.main(["input.tsv", "out", "--all-samples"])
        self.assertEqual(status, 2)

    def test_main_rejects_sample_id_in_batch_mode(self):
        from epg_renderer import cli

        status = cli.main(["input.tsv", "out", "--all-samples", "--sample-id", "S1"])
        self.assertEqual(status, 2)

    def test_expected_render_error_is_concise(self):
        import contextlib
        import io
        from unittest import mock

        from epg_renderer import cli

        error = io.StringIO()
        with (
            mock.patch.object(
                cli, "render_genemapper_epg_report", side_effect=ValueError("bad input")
            ),
            contextlib.redirect_stderr(error),
        ):
            status = cli.main(["input.tsv", "out.svg"])
        self.assertEqual(status, 2)
        self.assertEqual(error.getvalue(), "epg-render: error: bad input\n")
        self.assertNotIn("Traceback", error.getvalue())
