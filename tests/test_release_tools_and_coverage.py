from __future__ import annotations

import json
import os
import tempfile
import unittest
from collections import OrderedDict
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from unittest import mock

import epg_renderer.batch as batch
import epg_renderer.kit_registry as kit_registry
import epg_renderer.render_io as render_io
import tools.release_tools as release_tools
from epg_renderer import (
    load_kit,
    load_project,
)
from epg_renderer.kit_registry import DuplicateKitDefinitionError, KitSchemaError
from epg_renderer.kit_workflow import Confidence, KitMatch, KitResolutionError
from epg_renderer.models import GeneMapperProject, SampleCall
from epg_renderer.parser import GeneMapperParserError
from epg_renderer.positions import PositionModelError
from epg_renderer.render_options import (
    RasterRenderError,
    RasterRenderOptions,
    SampleSelectionError,
    SvgRenderError,
    SvgRenderOptions,
)
from tools.coverage_policy import COVERAGE_TARGETS
from tools.release_tools import (
    ReleaseError,
    build_source_archive,
    is_release_source,
    project_version,
    source_files,
    verify_manifest,
    verify_source_archive,
)
from tools.run_coverage_checks import evaluate_coverage_payload

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).with_name("fixtures") / "globalfiler_minimal.tsv"


def _write(directory: str, name: str, text: str, *, encoding: str = "utf-8") -> Path:
    path = Path(directory) / name
    path.write_text(text, encoding=encoding)
    return path


def _minimal_project(*sample_ids: str) -> GeneMapperProject:
    samples: OrderedDict[str, SampleCall] = OrderedDict()
    for sample_id in sample_ids:
        samples[sample_id] = SampleCall(sample_id)
    return GeneMapperProject(
        samples=samples,
        header=("Sample Name", "Marker", "Dye", "Allele 1", "Height 1"),
        delimiter="\t",
        sample_id_column="Sample Name",
    )


class CoveragePolicyTests(unittest.TestCase):
    @staticmethod
    def _payload(percent: float = 100.0) -> dict[str, object]:
        covered = round(percent)
        files = {
            f"src/epg_renderer/{target.module}": {
                "summary": {
                    "num_statements": 100,
                    "covered_lines": covered,
                    "num_branches": 100,
                    "covered_branches": covered,
                }
            }
            for target in COVERAGE_TARGETS
        }
        files["src/epg_renderer/gui.py"] = {
            "summary": {
                "num_statements": 100,
                "covered_lines": covered,
                "num_branches": 100,
                "covered_branches": covered,
            }
        }
        return {"files": files}

    def test_complete_payload_passes(self):
        self.assertEqual(evaluate_coverage_payload(self._payload()), [])

    def test_missing_module_and_low_coverage_are_reported(self):
        payload = self._payload()
        del payload["files"]["src/epg_renderer/parser.py"]
        payload["files"]["src/epg_renderer/batch.py"]["summary"]["covered_lines"] = 1
        payload["files"]["src/epg_renderer/batch.py"]["summary"]["covered_branches"] = 1
        failures = evaluate_coverage_payload(payload)
        self.assertTrue(
            any("parser.py" in failure and "missing" in failure for failure in failures)
        )
        self.assertTrue(any("batch.py" in failure and "below" in failure for failure in failures))

    def test_pyproject_enables_branch_coverage_for_package_source(self):
        source = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn("[tool.coverage.run]", source)
        self.assertIn("branch = true", source)
        self.assertIn('source = ["epg_renderer"]', source)
        self.assertIn('"build==1.3.0"', source)
        self.assertIn('"setuptools==82.0.1"', source)

    def test_coverage_runner_uses_an_isolated_data_file(self):
        source = (ROOT / "tools" / "run_coverage_checks.py").read_text(encoding="utf-8")
        self.assertIn('"COVERAGE_FILE": str(workspace / ".coverage")', source)
        self.assertIn('prefix="epg-renderer-coverage-"', source)


class ReleaseToolTests(unittest.TestCase):
    def test_required_repository_metadata_is_release_source(self):
        self.assertTrue(is_release_source(Path(".gitattributes")))
        self.assertTrue(is_release_source(Path("LICENSE")))
        self.assertFalse(is_release_source(Path("MANIFEST.sha256")))

    def test_generated_and_cache_paths_are_excluded(self):
        rejected = (
            Path("build/output.txt"),
            Path("src/epg_renderer/__pycache__/module.pyc"),
            Path("src/epg_renderer.egg-info/PKG-INFO"),
            Path("TEST_REPORT_v1.2.3.txt"),
            Path("EPG-Renderer_v1.2.3.zip"),
            Path("epg_renderer-1.2.3.tar.gz"),
            Path("epg_renderer-1.2.3-py3-none-any.whl"),
            Path("MANIFEST.sha256"),
        )
        for path in rejected:
            with self.subTest(path=path):
                self.assertFalse(is_release_source(path))
        self.assertTrue(is_release_source(Path("docs/API.md")))
        self.assertTrue(is_release_source(Path("src/epg_renderer/parser.py")))
        self.assertFalse(is_release_source(Path("private-notes.txt")))
        self.assertFalse(is_release_source(Path("secrets/config.env")))

    def test_prior_default_release_output_is_known_generated_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            source = root / "src/module.py"
            source.write_text("VALUE = 1\n", encoding="utf-8")
            output = root / "release/EPG-Renderer_v1.2.3.zip"
            output.parent.mkdir()
            output.write_bytes(b"previous release")

            self.assertEqual(source_files(root), (source,))

    def test_unapproved_source_file_aborts_release_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            (root / "src/module.py").write_text("VALUE = 1\n", encoding="utf-8")
            (root / ".env").write_text("SECRET=value\n", encoding="utf-8")
            with self.assertRaisesRegex(ReleaseError, "Unapproved files"):
                source_files(root)

    def test_copy_variant_check_scripts_are_not_release_sources(self):
        for name in (
            "tools/run_all_tests_2.py",
            "tools/run_coverage_checks_2.py",
            "tools/run_quality_checks_2.py",
            "tools/run_release_checks_2.py",
        ):
            with self.subTest(name=name):
                self.assertFalse(is_release_source(Path(name)))

    def test_release_runner_does_not_repeat_the_full_test_suite(self):
        source = (ROOT / "tools" / "run_release_checks.py").read_text(encoding="utf-8")
        self.assertNotIn('"tools.run_all_tests"', source)
        self.assertIn('"tools.run_coverage_checks"', source)

    def test_build_is_isolated_and_source_check_is_a_smoke_test(self):
        source = (ROOT / "tools" / "release_tools.py").read_text(encoding="utf-8")
        self.assertNotIn('"--no-isolation"', source)
        self.assertIn('"tests/smoke/source_smoke_test.py"', source)

    def test_clean_environment_preserves_posix_interpreter_runtime_paths(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            mock.patch.object(release_tools.venv, "EnvBuilder") as builder_class,
        ):
            workspace = Path(directory)
            environment, python = release_tools._create_clean_environment(workspace, "clean")

        builder_class.assert_called_once_with(
            with_pip=True,
            clear=True,
            symlinks=os.name != "nt",
        )
        builder_class.return_value.create.assert_called_once_with(workspace / "clean")
        self.assertEqual(environment, workspace / "clean")
        self.assertEqual(python, release_tools._venv_python(environment))

    def test_release_checks_minimal_and_raster_installations(self):
        source = (ROOT / "tools" / "release_tools.py").read_text(encoding="utf-8")
        self.assertIn("def test_minimal_installation(", source)
        self.assertIn("def test_raster_installation(", source)
        self.assertIn("_run_source_tests(python, source_root", source)
        self.assertIn('f"{wheel}[raster]"', source)

    def test_optional_test_dependencies_are_guarded(self):
        for name in ("test_cli.py", "test_raster.py"):
            source = (ROOT / "tests" / name).read_text(encoding="utf-8")
            self.assertIn("RASTER_DEPENDENCIES_AVAILABLE", source)
            self.assertIn('find_spec("PIL")', source)
            self.assertNotIn("\nfrom PIL import Image\n", source)

    def test_ci_matrix_covers_supported_python_versions_and_platforms(self):
        source = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        for platform in ("ubuntu-latest", "windows-latest", "macos-latest"):
            self.assertIn(platform, source)
        for version in ("3.10", "3.11", "3.12", "3.13", "3.14"):
            self.assertIn(f'"{version}"', source)
        self.assertEqual(source.count("runs-on: ${{ matrix.os }}"), 2)

    def test_ci_runs_the_complete_release_preflight(self):
        source = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("python -m tools.run_release_checks", source)

    def test_source_archive_manifests_license_and_attributes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            (root / "src/epg_renderer").mkdir(parents=True)
            (root / "pyproject.toml").write_text(
                '[project]\nname = "epg-renderer"\nversion = "1.2.3"\n', encoding="utf-8"
            )
            (root / "src/epg_renderer/version.py").write_text(
                '__version__ = "1.2.3"\n', encoding="utf-8"
            )
            (root / ".gitattributes").write_text("* text=auto\n", encoding="utf-8")
            (root / "LICENSE").write_text("BSD 3-Clause test license\n", encoding="utf-8")
            archive = Path(directory) / "EPG-Renderer_v1.2.3.zip"

            build_source_archive(root, archive, epoch=1784592000)
            extracted = verify_source_archive(archive)
            try:
                manifest = (extracted / "MANIFEST.sha256").read_text(encoding="utf-8")
                self.assertIn("  .gitattributes\n", manifest)
                self.assertIn("  LICENSE\n", manifest)
            finally:
                import shutil

                shutil.rmtree(extracted.parent)

    def test_source_archive_is_byte_reproducible_and_manifested(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            (root / "src/epg_renderer").mkdir(parents=True)
            (root / "pyproject.toml").write_text(
                '[project]\nname = "epg-renderer"\nversion = "1.2.3"\n', encoding="utf-8"
            )
            (root / "src/epg_renderer/version.py").write_text(
                '__version__ = "1.2.3"\n', encoding="utf-8"
            )
            (root / "src/epg_renderer/module.py").write_text("VALUE = 1\n", encoding="utf-8")
            first = Path(directory) / "one" / "EPG-Renderer_v1.2.3.zip"
            second = Path(directory) / "two" / "EPG-Renderer_v1.2.3.zip"
            build_source_archive(root, first, epoch=1784592000)
            build_source_archive(root, second, epoch=1784592000)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            extracted = verify_source_archive(first)
            try:
                self.assertEqual(project_version(extracted), "1.2.3")
                self.assertTrue((extracted / "MANIFEST.sha256").is_file())
            finally:
                import shutil

                shutil.rmtree(extracted.parent)

    def test_manifest_rejects_modified_and_unexpected_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "data.txt"
            data.write_text("original", encoding="utf-8")
            import hashlib

            digest = hashlib.sha256(data.read_bytes()).hexdigest()
            (root / "MANIFEST.sha256").write_text(f"{digest}  data.txt\n", encoding="utf-8")
            verify_manifest(root)
            data.write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(ReleaseError, "digest mismatch"):
                verify_manifest(root)
            data.write_text("original", encoding="utf-8")
            (root / "extra.txt").write_text("extra", encoding="utf-8")
            with self.assertRaisesRegex(ReleaseError, "file set differs"):
                verify_manifest(root)

    def test_version_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src/epg_renderer").mkdir(parents=True)
            (root / "pyproject.toml").write_text('[project]\nversion = "1.2.3"\n', encoding="utf-8")
            (root / "src/epg_renderer/version.py").write_text(
                '__version__ = "1.2.2"\n', encoding="utf-8"
            )
            with self.assertRaisesRegex(ReleaseError, "different versions"):
                project_version(root)


class ParserBoundaryTests(unittest.TestCase):
    def test_missing_file_and_unsupported_delimiter(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(GeneMapperParserError, "does not exist"):
                load_project(Path(directory) / "missing.tsv")
            path = _write(directory, "input.txt", "Sample Name|Marker|Dye|Allele 1|Height 1\n")
            with self.assertRaisesRegex(GeneMapperParserError, "Unsupported delimiter"):
                load_project(path, delimiter="|")

    def test_empty_or_blank_headers_and_missing_height_header(self):
        with tempfile.TemporaryDirectory() as directory:
            blank_column = _write(
                directory, "blank-column.tsv", "Sample Name\tMarker\t\tAllele 1\tHeight 1\n"
            )
            with self.assertRaisesRegex(GeneMapperParserError, "Blank column"):
                load_project(blank_column, delimiter="\t")
            no_height = _write(
                directory,
                "no-height.tsv",
                "Sample Name\tMarker\tDye\tAllele 1\nS1\tD3S1358\tB\t15\n",
            )
            with self.assertRaisesRegex(GeneMapperParserError, "No columns such as 'Height 1'"):
                load_project(no_height, delimiter="\t")

    def test_header_only_and_permissive_missing_height(self):
        with tempfile.TemporaryDirectory() as directory:
            header_only = _write(
                directory, "header.tsv", "Sample Name\tMarker\tDye\tAllele 1\tHeight 1\n"
            )
            with self.assertRaisesRegex(GeneMapperParserError, "No sample rows"):
                load_project(header_only, delimiter="\t")
            no_height = _write(
                directory,
                "permissive.tsv",
                "Sample Name\tMarker\tDye\tAllele 1\tHeight 1\nS1\tD3S1358\tB\t15\t\n",
            )
            project = load_project(no_height, delimiter="\t", require_height=False)
            call = project.sample("S1").markers["D3S1358"].alleles[0]
            self.assertEqual(call.allele, "15")
            self.assertIsNone(call.height)

    def test_explicit_invalid_encoding_is_wrapped(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.tsv"
            path.write_bytes(b"\xff\xfe\xfd")
            with self.assertRaisesRegex(GeneMapperParserError, "Could not decode"):
                load_project(path, encoding="utf-8")


class RegistryBoundaryTests(unittest.TestCase):
    def tearDown(self):
        kit_registry.clear_registry_cache()

    def test_empty_registry_and_invalid_resource_are_wrapped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data/kits").mkdir(parents=True)
            with mock.patch.object(kit_registry, "files", return_value=root):
                kit_registry.clear_registry_cache()
                with self.assertRaisesRegex(KitSchemaError, "No bundled"):
                    kit_registry.available_kit_names()
            (root / "data/kits/bad.json").write_text("{", encoding="utf-8")
            with mock.patch.object(kit_registry, "files", return_value=root):
                kit_registry.clear_registry_cache()
                with self.assertRaisesRegex(KitSchemaError, "Could not read"):
                    kit_registry.available_kit_names()

    def test_shared_alias_between_resources_is_rejected(self):
        payload = json.loads(
            (ROOT / "src/epg_renderer/data/kits/globalfiler_v1.json").read_text(encoding="utf-8")
        )
        second = json.loads(json.dumps(payload))
        second["kit"]["name"] = "GlobalFiler Clone"
        second["kit"]["display_name"] = "GlobalFiler Clone"
        second["kit"]["aliases"] = ["GFI"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            kits = root / "data/kits"
            kits.mkdir(parents=True)
            (kits / "one.json").write_text(json.dumps(payload), encoding="utf-8")
            (kits / "two.json").write_text(json.dumps(second), encoding="utf-8")
            with mock.patch.object(kit_registry, "files", return_value=root):
                kit_registry.clear_registry_cache()
                with self.assertRaisesRegex(DuplicateKitDefinitionError, "shared"):
                    kit_registry.available_kit_names()


class PositionBoundaryTests(unittest.TestCase):
    def test_coordinate_map_and_missing_marker_paths(self):
        model = load_kit("GlobalFiler").coordinate_model
        marker = model.marker("D3S1358")
        self.assertEqual(
            marker.coordinate_map()[marker.coordinates[0].allele], marker.coordinates[0].nominal_bp
        )
        with self.assertRaises(KeyError):
            model.marker("NOT_A_MARKER")
        incomplete = replace(model, markers=model.markers[1:])
        with self.assertRaises(KeyError):
            incomplete.marker("D3S1358")

    def test_coordinate_model_validation_rejects_all_structural_inconsistencies(self):
        model = load_kit("GlobalFiler").coordinate_model
        ngm = load_kit("NGM").kit
        with self.assertRaisesRegex(PositionModelError, "does not match"):
            model.validate(ngm)
        with self.assertRaisesRegex(PositionModelError, "exact-bin flag"):
            replace(model, exact_bin_centres=True).validate()
        with self.assertRaisesRegex(PositionModelError, "marker order"):
            replace(model, markers=tuple(reversed(model.markers))).validate()
        first = model.markers[0]
        modified = replace(model, markers=(replace(first, dye="wrong"), *model.markers[1:]))
        with self.assertRaisesRegex(PositionModelError, "Dye mismatch"):
            modified.validate()
        modified = replace(
            model, markers=(replace(first, range_min_bp=first.range_max_bp), *model.markers[1:])
        )
        with self.assertRaisesRegex(PositionModelError, "Invalid marker range"):
            modified.validate()
        modified = replace(
            model, markers=(replace(first, coordinates=first.coordinates[1:]), *model.markers[1:])
        )
        with self.assertRaisesRegex(PositionModelError, "do not match the ladder"):
            modified.validate()
        duplicate = replace(first.coordinates[1], nominal_bp=first.coordinates[0].nominal_bp)
        modified = replace(
            model,
            markers=(
                replace(
                    first, coordinates=(first.coordinates[0], duplicate, *first.coordinates[2:])
                ),
                *model.markers[1:],
            ),
        )
        with self.assertRaisesRegex(PositionModelError, "increase uniquely"):
            modified.validate()
        outside = replace(first.coordinates[0], nominal_bp=first.range_min_bp - Decimal("1"))
        modified = replace(
            model,
            markers=(
                replace(first, coordinates=(outside, *first.coordinates[1:])),
                *model.markers[1:],
            ),
        )
        with self.assertRaisesRegex(PositionModelError, "outside the marker range"):
            modified.validate()


class BatchBoundaryTests(unittest.TestCase):
    def test_empty_project_and_non_genemapper_kit_write_batch_manifest(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            mock.patch.object(batch, "read_genotypes_table", return_value=_minimal_project()),
        ):
            output = Path(directory) / "empty"
            with self.assertRaises(SampleSelectionError):
                batch.render_genemapper_batch("input.tsv", output)
            manifest = json.loads((output / "epg_batch_manifest.json").read_text())
            self.assertIn("SampleSelectionError", manifest["batch_error"])
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "unsupported"
            with self.assertRaisesRegex(KitResolutionError, "not enabled"):
                batch.render_genemapper_batch(FIXTURE, output, kit_name="PowerPlex 35GY")
            manifest = json.loads((output / "epg_batch_manifest.json").read_text())
            self.assertEqual(manifest["kit_name"], "PowerPlex 35GY")

    def test_custom_sample_column_and_colliding_safe_names(self):
        content = "ID\tMarker\tDye\tAllele 1\tHeight 1\nA/B\tD3S1358\tB\t15\t100\nA?B\tD3S1358\tB\t15\t200\n"
        with tempfile.TemporaryDirectory() as directory:
            source = _write(directory, "samples.tsv", content)
            output = Path(directory) / "out"
            with mock.patch.object(
                batch,
                "render_positioned_sample_svg",
                return_value=(ROOT / "examples/globalfiler_example.svg").read_text(
                    encoding="utf-8"
                ),
            ):
                result = batch.render_genemapper_batch(
                    source, output, kit_name="GlobalFiler", sample_id_column="ID"
                )
            self.assertEqual(
                [item.output_path.name for item in result.items], ["A_B.svg", "A_B_2.svg"]
            )

    def test_mixed_auto_detected_kits_are_rejected(self):
        project = _minimal_project("one", "two")
        global_match = KitMatch(load_kit("GlobalFiler").kit, Confidence.EXACT, 1, 1, 1, (), (), ())
        ngm_match = KitMatch(load_kit("NGM").kit, Confidence.EXACT, 1, 1, 1, (), (), ())
        with (
            tempfile.TemporaryDirectory() as directory,
            mock.patch.object(batch, "read_genotypes_table", return_value=project),
            mock.patch.object(batch, "resolve_kit", side_effect=(global_match, ngm_match)),
            self.assertRaisesRegex(SvgRenderError, "one common kit"),
        ):
            batch.render_genemapper_batch(
                "input.tsv", Path(directory) / "out", continue_on_error=False
            )


class RenderValidationBoundaryTests(unittest.TestCase):
    def test_svg_and_raster_output_boundary_errors(self):
        svg = (ROOT / "examples/globalfiler_example.svg").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(SvgRenderError, "must use the .svg"):
                render_io.write_svg(svg, Path(directory) / "out.png")
            with self.assertRaisesRegex(RasterRenderError, "must use .png"):
                render_io.write_raster_image(svg, Path(directory) / "out.svg")
            path = Path(directory) / "out.svg"
            render_io.write_epg_output(svg, path, raster_options=RasterRenderOptions())
            self.assertTrue(path.is_file())

    def test_invalid_svg_dimensions_and_rasterizer_error_are_wrapped(self):
        invalid = '<?xml version="1.0" encoding="UTF-8"?>\n<svg xmlns="http://www.w3.org/2000/svg" width="bad" height="10" data-epg-renderer-version="1.2.3"></svg>'
        cairo = mock.Mock()
        image = mock.Mock()
        with (
            tempfile.TemporaryDirectory() as directory,
            mock.patch.object(render_io, "_load_raster_dependencies", return_value=(cairo, image)),
            self.assertRaisesRegex(RasterRenderError, "integer pixel"),
        ):
            render_io.write_raster_image(invalid, Path(directory) / "out.png")
        svg = (ROOT / "examples/globalfiler_example.svg").read_text(encoding="utf-8")
        cairo.svg2png.side_effect = RuntimeError("boom")
        with (
            tempfile.TemporaryDirectory() as directory,
            mock.patch.object(render_io, "_load_raster_dependencies", return_value=(cairo, image)),
            self.assertRaisesRegex(RasterRenderError, "Could not rasterize"),
        ):
            render_io.write_raster_image(svg, Path(directory) / "out.png")

    def test_jpeg_encoder_failure_and_invalid_svg_documents(self):
        svg = (ROOT / "examples/globalfiler_example.svg").read_text(encoding="utf-8")
        cairo = mock.Mock()
        cairo.svg2png.return_value = b"png"
        image = mock.Mock()
        image.open.side_effect = RuntimeError("jpeg failure")
        with (
            tempfile.TemporaryDirectory() as directory,
            mock.patch.object(render_io, "_load_raster_dependencies", return_value=(cairo, image)),
            self.assertRaisesRegex(RasterRenderError, "Could not encode JPEG"),
        ):
            render_io.write_raster_image(svg, Path(directory) / "out.jpg")
        for invalid, message in (
            ("<svg/>", "not a complete"),
            ('<?xml version="1.0" encoding="UTF-8"?><svg', "not well-formed"),
            (
                '<?xml version="1.0" encoding="UTF-8"?><svg xmlns="http://www.w3.org/2000/svg"/>',
                "not an EPG-Renderer",
            ),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(SvgRenderError, message):
                render_io._validate_svg_document(invalid)

    def test_render_option_validation_error_paths(self):
        invalid_options = (
            (replace(SvgRenderOptions(), header_height=10), "Header or footer"),
            (replace(SvgRenderOptions(), left_margin=10), "margins"),
            (
                replace(SvgRenderOptions(), width=700, left_margin=200, right_margin=101),
                "Margins leave",
            ),
            (replace(SvgRenderOptions(), x_tick_interval_bp=0), "positive"),
            (replace(SvgRenderOptions(), fixed_max_rfu=True), "integer or None"),
            (replace(SvgRenderOptions(), fixed_max_rfu=0), "must be positive"),
            (replace(SvgRenderOptions(), yellow_channel_mode="invalid"), "Unknown yellow"),
            (replace(SvgRenderOptions(), title=123), "title must be"),
        )
        from epg_renderer.render_options import validate_raster_options, validate_svg_options

        for options, message in invalid_options:
            with self.subTest(message=message), self.assertRaisesRegex(SvgRenderError, message):
                validate_svg_options(options)
        for options, message in (
            (RasterRenderOptions(scale=True), "finite number"),
            (RasterRenderOptions(jpeg_quality=True), "integer"),
            (RasterRenderOptions(jpeg_optimize=1), "boolean"),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(RasterRenderError, message):
                validate_raster_options(options)


if __name__ == "__main__":
    unittest.main()
