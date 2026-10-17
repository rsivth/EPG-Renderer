"""EPG-Renderer reads GeneMapper exports through the bundled STRio package (0.16.0).

These tests protect three promises of that change: the bundled copy is exactly the
recorded STRio release, the renderer's parser interface (names, exception classes,
messages, 32,767-RFU ceiling) is unchanged, and the bundled package travels with every
distribution form without a runtime dependency.
"""

from __future__ import annotations

import ast
import codecs
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from epg_renderer import load_project
from epg_renderer._vendor import strio
from epg_renderer.parser import (
    DuplicateHeaderError,
    DuplicateMarkerError,
    GeneMapperParserError,
    MissingRequiredColumnError,
    NumericConversionError,
    read_genotypes_table,
)
from tools.release_tools import is_release_source
from tools.vendor_strio import build_manifest, verify_vendored

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "src" / "epg_renderer" / "_vendor"
HEADER = "Sample Name\tMarker\tDye\tAllele 1\tHeight 1\n"


def _write(case: unittest.TestCase, data: bytes) -> Path:
    directory = Path(tempfile.mkdtemp())
    case.addCleanup(shutil.rmtree, directory)
    path = directory / "export.txt"
    path.write_bytes(data)
    return path


class BundledCopyTests(unittest.TestCase):
    def test_bundled_copy_matches_its_manifest(self) -> None:
        self.assertEqual(verify_vendored(), [])

    def test_manifest_names_the_bundled_release(self) -> None:
        manifest = json.loads((VENDOR / "VENDORED.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], strio.__version__)
        self.assertEqual(manifest["tag"], f"v{strio.__version__}")
        self.assertEqual(manifest["source"], "https://github.com/rsivth/strio")
        self.assertEqual(manifest["license"], "BSD-3-Clause")
        self.assertIn("LICENSE", manifest["files"])

    def test_bundled_version_is_at_least_the_reader_used_for_0_16_0(self) -> None:
        version = tuple(int(part) for part in strio.__version__.split("."))
        self.assertGreaterEqual(version, (0, 2, 0))

    def test_edited_extra_or_missing_files_are_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            copy = Path(directory) / "_vendor"
            shutil.copytree(VENDOR, copy, ignore=shutil.ignore_patterns("__pycache__"))
            (copy / "strio" / "model.py").write_text("changed\n", encoding="utf-8")
            (copy / "strio" / "extra.py").write_text("", encoding="utf-8")
            (copy / "strio" / "markers.py").unlink()
            problems = verify_vendored(copy)
        self.assertIn("Bundled file model.py differs from the recorded release.", problems)
        self.assertIn("Unrecorded bundled file extra.py.", problems)
        self.assertIn("Missing bundled file markers.py.", problems)

    def test_missing_manifest_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(verify_vendored(Path(directory)), ["Missing manifest VENDORED.json."])

    def test_manifest_builder_records_every_file_and_the_license(self) -> None:
        manifest = build_manifest(VENDOR / "strio", VENDOR / "strio" / "LICENSE")
        recorded = json.loads((VENDOR / "VENDORED.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest, recorded)

    def test_bundled_package_imports_itself_only_relatively(self) -> None:
        findings = []
        for path in sorted((VENDOR / "strio").rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    names = [node.module or ""]
                else:
                    continue
                if any(name == "strio" or name.startswith("strio.") for name in names):
                    findings.append(f"{path.name}:{node.lineno}")
        self.assertEqual(findings, [])


class ParserInterfaceTests(unittest.TestCase):
    def test_renderer_exceptions_keep_their_names_and_hierarchy(self) -> None:
        pairs = (
            (MissingRequiredColumnError, strio.MissingColumnError),
            (DuplicateHeaderError, strio.DuplicateColumnError),
            (DuplicateMarkerError, strio.DuplicateLocusError),
            (NumericConversionError, strio.NumericValueError),
        )
        for renderer_type, reader_type in pairs:
            with self.subTest(renderer_type=renderer_type.__name__):
                self.assertTrue(issubclass(renderer_type, GeneMapperParserError))
                self.assertTrue(issubclass(renderer_type, reader_type))
        self.assertTrue(issubclass(GeneMapperParserError, ValueError))
        self.assertTrue(issubclass(GeneMapperParserError, strio.ParseError))

    def test_reader_errors_surface_as_renderer_classes_with_unchanged_messages(self) -> None:
        cases = (
            ("Sample Name\tDye\tAllele 1\tHeight 1\nS\tB\t15\t1\n", MissingRequiredColumnError),
            (
                "Sample Name\tMarker\tAllele 1\tallele 1\tHeight 1\nS\tvWA\t1\t1\t1\n",
                DuplicateHeaderError,
            ),
            (HEADER + "S\tvWA\tB\t14\t1\nS\tVWA\tB\t15\t1\n", DuplicateMarkerError),
            (HEADER + "S\tvWA\tB\t14\t-1\n", NumericConversionError),
            ('Sample Name,Marker,Allele 1,Height 1\nS"1,vWA,14,1\n', GeneMapperParserError),
        )
        for text, expected in cases:
            with self.subTest(expected=expected.__name__):
                path = _write(self, text.encode("utf-8"))
                with self.assertRaises(expected) as caught:
                    read_genotypes_table(path)
                self.assertIs(type(caught.exception), expected)
                self.assertIsInstance(caught.exception.__cause__, strio.ParseError)
                self.assertEqual(str(caught.exception), str(caught.exception.__cause__))

    def test_rfu_ceiling_is_applied_by_the_renderer(self) -> None:
        path = _write(self, (HEADER + "S\tvWA\tB\t14\t32768\n").encode("utf-8"))
        with self.assertRaisesRegex(NumericConversionError, "32,767"):
            read_genotypes_table(path)

    def test_export_mode_is_validated_before_the_file_is_read(self) -> None:
        with self.assertRaisesRegex(GeneMapperParserError, "export_mode must be"):
            read_genotypes_table(ROOT / "missing.txt", export_mode="other")

    def test_export_mode_is_normalized_and_kept_on_the_project(self) -> None:
        path = _write(self, (HEADER + "S\tvWA\tB\t14\t100\n").encode("utf-8"))
        self.assertEqual(
            read_genotypes_table(path, export_mode=" With_Stutter ").export_mode, "with_stutter"
        )

    def test_project_is_built_from_renderer_models_only(self) -> None:
        project = load_project(ROOT / "tests" / "fixtures" / "globalfiler_minimal.tsv")
        sample = project.sample("S1")
        call = sample.markers["TH01"].alleles[1]
        self.assertEqual(type(project).__module__, "epg_renderer.models")
        self.assertEqual(type(sample).__module__, "epg_renderer.models")
        self.assertEqual(type(call).__module__, "epg_renderer.models")
        self.assertEqual((call.allele_index, call.allele, call.height), (2, "9.3", 750))


class ReaderImprovementTests(unittest.TestCase):
    def test_utf16_export_with_byte_order_mark_is_read(self) -> None:
        text = HEADER + "Pröbe\tvWA\tB\t14\t100\n"
        path = _write(self, codecs.BOM_UTF16_LE + text.encode("utf-16-le"))
        project = load_project(path)
        self.assertEqual(project.sample_ids, ("Pröbe",))
        self.assertEqual(project.encoding, "utf-16")

    def test_utf16_without_byte_order_mark_names_the_cause(self) -> None:
        path = _write(self, (HEADER + "S\tvWA\tB\t14\t100\n").encode("utf-16-le"))
        with self.assertRaisesRegex(GeneMapperParserError, "UTF-16"):
            load_project(path)


class BundledReaderFixTests(unittest.TestCase):
    """Fixes that arrive with STRio 0.2.x, as the renderer's user sees them."""

    def test_very_long_numbers_are_parser_errors_again(self) -> None:
        # 0.15.1 raised NumericConversionError; the first 0.16.0 candidate let a plain
        # ValueError escape for values beyond 4,300 digits.
        huge = "9" * 5000
        cases = (
            (HEADER.replace("Height 1", "Height 1\tArea 1"), f"S\tvWA\tB\t14\t1\t{huge}\n"),
            (HEADER, f"S\tvWA\tB\t14\t{huge}\n"),
        )
        for header, row in cases:
            path = _write(self, (header + row).encode("utf-8"))
            with self.subTest(header=header), self.assertRaises(NumericConversionError) as caught:
                read_genotypes_table(path)
            self.assertLess(len(str(caught.exception)), 200)

    def test_columns_equal_except_spacing_are_rejected(self) -> None:
        text = "Sample Name\tSample  Name\tMarker\tAllele 1\tHeight 1\nA\tB\tvWA\t14\t1\n"
        with self.assertRaisesRegex(DuplicateHeaderError, "differ only in spacing"):
            read_genotypes_table(_write(self, text.encode("utf-8")))

    def test_digits_of_other_scripts_are_rejected(self) -> None:
        path = _write(self, (HEADER + "S\tvWA\tB\t14\t\u0661\u0662\u0663\n").encode("utf-8"))
        with self.assertRaises(NumericConversionError):
            read_genotypes_table(path)

    def test_sizes_with_more_than_six_decimal_places_are_rejected(self) -> None:
        text = "Sample Name\tMarker\tAllele 1\tHeight 1\tSize 1\nS\tvWA\t14\t1\t160.1234567\n"
        with self.assertRaisesRegex(NumericConversionError, "more than 6 decimal places"):
            read_genotypes_table(_write(self, text.encode("utf-8")))

    def test_messages_name_the_exported_column(self) -> None:
        text = "Sample Name\tMarker\tAllele 1\tHeight 1\tPeak Area 1\nS\tvWA\t14\t1\tx\n"
        with self.assertRaisesRegex(NumericConversionError, "'Peak Area 1'"):
            read_genotypes_table(_write(self, text.encode("utf-8")))

    def test_column_names_with_a_line_break_are_read(self) -> None:
        # 0.15.1 and 0.16.0 rejected this with "Could not detect CSV delimiter".
        text = 'Sample Name,Marker,Allele 1,Height 1,"Long\nNote"\nS,vWA,14,100,ok\n'
        project = read_genotypes_table(_write(self, text.encode("utf-8")))
        self.assertEqual(project.delimiter, ",")
        self.assertEqual(project.header[-1], "Long\nNote")
        self.assertEqual(project.samples["S"].markers["vWA"].alleles[0].allele, "14")

    def test_bundled_reader_describes_its_table_separately(self) -> None:
        dataset = strio.read_genemapper(ROOT / "tests" / "fixtures" / "ngm_minimal.tsv")
        self.assertEqual(dataset.source.require_table().delimiter, "\t")


class DistributionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    def test_no_runtime_dependency_is_added(self) -> None:
        self.assertIn("\ndependencies = []\n", self.pyproject)

    def test_wheel_contains_the_bundled_packages_and_their_data(self) -> None:
        for package in ("_vendor", "_vendor/strio", "_vendor/strio/formats"):
            with self.subTest(package=package):
                init = ROOT / "src" / "epg_renderer" / package / "__init__.py"
                self.assertTrue(init.is_file())
        self.assertIn('"epg_renderer._vendor" = ["VENDORED.json"]', self.pyproject)
        self.assertIn('"epg_renderer._vendor.strio" = ["LICENSE", "py.typed"]', self.pyproject)

    def test_source_release_includes_the_bundled_copy_and_the_vendoring_tool(self) -> None:
        for relative in (
            "src/epg_renderer/_vendor/VENDORED.json",
            "src/epg_renderer/_vendor/strio/LICENSE",
            "src/epg_renderer/_vendor/strio/formats/genemapper.py",
            "tools/vendor_strio.py",
        ):
            with self.subTest(path=relative):
                self.assertTrue(is_release_source(Path(relative)))

    def test_lint_and_coverage_leave_the_bundled_copy_to_its_own_project(self) -> None:
        self.assertIn('    "src/epg_renderer/_vendor/strio",\n', self.pyproject)
        self.assertIn('omit = ["*/epg_renderer/_vendor/strio/*"]', self.pyproject)

    def test_bundled_files_keep_their_bytes_on_every_platform(self) -> None:
        attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()
        self.assertIn("src/epg_renderer/_vendor/strio/** -text", attributes)


if __name__ == "__main__":
    unittest.main()
