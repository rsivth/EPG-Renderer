from __future__ import annotations

import importlib.util
import json
import re
import unittest
from pathlib import Path

import epg_renderer
from epg_renderer import (
    list_kits,
    load_kit,
)

ROOT = Path(__file__).resolve().parents[1]


class PublicApiCleanupTests(unittest.TestCase):
    def test_compatibility_only_modules_are_absent(self) -> None:
        self.assertIsNone(importlib.util.find_spec("epg_renderer.detection"))
        self.assertIsNone(importlib.util.find_spec("epg_renderer.renderer"))

    def test_removed_aliases_and_constants_are_not_public(self) -> None:
        removed = {
            "AVAILABLE_KITS",
            "GLOBALFILER",
            "NGM",
            "JsonKitCoordinateModel",
            "get_registered_coordinate_model",
            "get_registered_kit",
            "normalize_dye",
            "position_registered_sample",
        }
        self.assertTrue(removed.isdisjoint(epg_renderer.__all__))
        for name in removed:
            with self.subTest(name=name):
                self.assertFalse(hasattr(epg_renderer, name))


class SchemaConsolidationTests(unittest.TestCase):
    def test_only_one_kit_schema_resource_exists(self) -> None:
        resources = sorted((ROOT / "src/epg_renderer/data").glob("kit_definition_schema*.json"))
        self.assertEqual([path.name for path in resources], ["kit_definition_schema.json"])

    def test_all_bundled_profiles_use_the_single_schema_version(self) -> None:
        self.assertEqual(len(tuple(profile.kit.name for profile in list_kits())), 14)
        for name in tuple(profile.kit.name for profile in list_kits()):
            with self.subTest(kit=name):
                load_kit(name)
        for path in sorted((ROOT / "src/epg_renderer/data/kits").glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], "1.1")
            self.assertIn(
                payload["metadata"]["created_for"], {"EPG-Renderer v0.10.4", "EPG-Renderer v0.11.0"}
            )


class CurrentSourceTreeTests(unittest.TestCase):
    def test_test_suite_has_no_version_or_phase_bound_class_names(self) -> None:
        pattern = re.compile("^class\\s+(?:V\\d|Phase\\d)", re.MULTILINE)
        offenders = [
            path.name
            for path in sorted((ROOT / "tests").glob("test_*.py"))
            if pattern.search(path.read_text(encoding="utf-8"))
        ]
        self.assertEqual(offenders, [])

    def test_test_runner_uses_plain_discovery_without_supersession_bookkeeping(self) -> None:
        source = (ROOT / "tools" / "run_all_tests.py").read_text(encoding="utf-8")
        self.assertNotIn("SUPERSEDED", source.upper())
        self.assertNotIn("excluded", source.casefold())
        self.assertIn("discover", source)

    def test_tool_modules_are_canonical_and_have_no_copy_variants(self) -> None:
        expected = {
            "run_all_tests.py",
            "run_coverage_checks.py",
            "run_quality_checks.py",
            "run_release_checks.py",
        }
        actual = {
            path.name for path in (ROOT / "tools").glob("*.py") if path.name.startswith("run_")
        }
        self.assertEqual(actual, expected)
        self.assertFalse(any(path.stem.endswith("_2") for path in (ROOT / "tools").glob("*.py")))
        self.assertTrue((ROOT / "tests" / "smoke" / "source_smoke_test.py").is_file())

    def test_docs_and_examples_contain_only_current_unversioned_artifacts(self) -> None:
        docs = {
            path.relative_to(ROOT / "docs").as_posix()
            for path in (ROOT / "docs").rglob("*")
            if path.is_file()
        }
        self.assertEqual(
            docs,
            {
                "API.md",
                "ARCHITECTURE.md",
                "CLI.md",
                "CODE_DOCUMENTATION.md",
                "COORDINATE_MODEL.md",
                "DEVELOPMENT.md",
                "GENEMAPPER.md",
                "GETTING_STARTED.md",
                "INSTALLATION.md",
                "KIT_FORMAT.md",
                "PYTHON.md",
                "SOURCES.md",
                "index.md",
            },
        )
        examples = {path.name for path in (ROOT / "examples").iterdir() if path.is_file()}
        self.assertEqual(
            examples,
            {
                "globalfiler_example.svg",
                "ngm_example.svg",
                "esi17_two_person_mixture_example.svg",
                "ngm_detect_five_person_mixture_example.svg",
                "render_globalfiler_example.py",
                "render_ngm_example.py",
                "render_esi17_two_person_mixture_example.py",
                "render_ngm_detect_five_person_mixture_example.py",
                "update_examples.py",
            },
        )
        versioned = re.compile("_v\\d+\\.\\d+")
        self.assertFalse(any(versioned.search(name) for name in docs | examples))


if __name__ == "__main__":
    unittest.main()
