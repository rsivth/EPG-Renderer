from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SMOKE_PATH = ROOT / "tests" / "smoke" / "binary_smoke_test.py"


def _load_smoke_module() -> ModuleType:
    module_spec = importlib.util.spec_from_file_location("epg_renderer_binary_smoke", SMOKE_PATH)
    if module_spec is None or module_spec.loader is None:
        raise AssertionError("Could not load the binary smoke-test module.")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


class BinarySmokeInterfaceTests(unittest.TestCase):
    def test_runner_is_standalone_and_covers_the_release_contract(self):
        source = SMOKE_PATH.read_text(encoding="utf-8")
        self.assertNotIn("import epg_renderer", source)
        self.assertNotIn("from epg_renderer", source)
        for phrase in (
            "--version",
            "--help",
            "--list-kits",
            "SVG rendering: passed",
            "JPEG rendering: passed",
            "Batch rendering: passed",
            "GUI startup dependencies: passed",
            "Isolated runtime: passed",
        ):
            self.assertIn(phrase, source)

    def test_isolated_environment_removes_python_and_external_library_paths(self):
        smoke = _load_smoke_module()
        environment = {
            "PATH": "with-python",
            "PYTHONPATH": "source",
            "PYTHONHOME": "runtime",
            "VIRTUAL_ENV": "venv",
            "CAIROCFFI_DLL_DIRECTORIES": "cairo",
            "SYSTEMROOT": "C:/Windows",
        }
        with (
            tempfile.TemporaryDirectory() as directory,
            mock.patch.dict(os.environ, environment, clear=True),
        ):
            isolated = smoke._isolated_environment(Path(directory))
        self.assertEqual(isolated["PATH"], "")
        self.assertNotIn("PYTHONPATH", isolated)
        self.assertNotIn("PYTHONHOME", isolated)
        self.assertNotIn("VIRTUAL_ENV", isolated)
        self.assertNotIn("CAIROCFFI_DLL_DIRECTORIES", isolated)
        self.assertEqual(isolated["SYSTEMROOT"], "C:/Windows")

    def test_output_validators_accept_canonical_binary_results(self):
        smoke = _load_smoke_module()
        smoke._verify_version("epg-render 0.13.37\n", "0.13.37")
        smoke._verify_help("usage: epg-render --all-samples --list-kits .svg .jpg")
        smoke._verify_kits("\n".join(smoke.EXPECTED_KITS) + "\n")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            svg = root / "single.svg"
            svg.write_text(
                '<svg data-epg-renderer-version="0.13.37" data-kit="GlobalFiler"/>',
                encoding="utf-8",
            )
            smoke._verify_svg(svg, "0.13.37")
            jpeg = root / "single.jpg"
            jpeg.write_bytes(b"\xff\xd8\xff" + b"x" * 1024 + b"\xff\xd9")
            smoke._verify_jpeg(jpeg)
            batch = root / "batch"
            batch.mkdir()
            batch_svg = batch / "S1.svg"
            batch_svg.write_text(svg.read_text(encoding="utf-8"), encoding="utf-8")
            (batch / "epg_batch_manifest.json").write_text(
                json.dumps(
                    {
                        "epg_renderer_version": "0.13.37",
                        "succeeded": 1,
                        "failed": 0,
                        "items": [{"output_file": "S1.svg"}],
                    }
                ),
                encoding="utf-8",
            )
            smoke._verify_batch(batch, "0.13.37")

    def test_output_validators_reject_wrong_version_and_kit_inventory(self):
        smoke = _load_smoke_module()
        with self.assertRaises(smoke.BinarySmokeError):
            smoke._verify_version("epg-render 0.13.36\n", "0.13.37")
        with self.assertRaises(smoke.BinarySmokeError):
            smoke._verify_kits("GlobalFiler\n")


if __name__ == "__main__":
    unittest.main()
