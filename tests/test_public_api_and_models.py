from __future__ import annotations

import tempfile
import unittest
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path

import epg_renderer
from epg_renderer import (
    list_kits,
    load_kit,
    load_project,
    match_kits,
    position_sample,
    render_batch,
    render_file,
    render_svg,
)
from epg_renderer.batch import BatchRenderItem, BatchRenderResult
from epg_renderer.domain import (
    BatchStatus,
    ExportCompatibility,
    KitType,
    MarkerMetadata,
    MarkerType,
    PeakHeightMode,
    ProfileOrigin,
    SourceReference,
)
from epg_renderer.kit_workflow import Confidence, KitMatch
from epg_renderer.kits import DyeChannel, KitDefinition, KitDefinitionError, MarkerDefinition
from epg_renderer.models import AlleleCall, GeneMapperProject, MarkerCall, SampleCall
from epg_renderer.positions import CoordinateKind, PositionedSample
from epg_renderer.render_options import OutputFormat

FIXTURE = Path(__file__).with_name("fixtures") / "globalfiler_minimal.tsv"
OPERATIONS = {
    "list_kits": list_kits,
    "load_kit": load_kit,
    "load_project": load_project,
    "match_kits": match_kits,
    "position_sample": position_sample,
    "render_batch": render_batch,
    "render_file": render_file,
    "render_svg": render_svg,
}


class PublicApiTests(unittest.TestCase):
    def test_package_root_exposes_only_version_and_canonical_operations(self) -> None:
        self.assertEqual(set(epg_renderer.__all__), {"__version__", *OPERATIONS})
        for name, function in OPERATIONS.items():
            self.assertIs(getattr(epg_renderer, name), function)

    def test_data_types_are_not_implicit_package_root_exports(self) -> None:
        for name in (
            "AlleleCall",
            "BatchRenderResult",
            "KitProfile",
            "SampleCall",
            "SvgRenderOptions",
        ):
            with self.subTest(name=name):
                self.assertFalse(hasattr(epg_renderer, name))

    def test_render_svg_rejects_kit_name_for_positioned_sample(self) -> None:
        positioned = position_sample(load_project(FIXTURE).sample("S1"), kit_name="GlobalFiler")
        with self.assertRaisesRegex(ValueError, "already positioned"):
            render_svg(positioned, kit_name="GlobalFiler")

    def test_release_smoke_probe_uses_only_canonical_root_api(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "tools" / "release_tools.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("e.list_kits()", source)
        self.assertNotIn("e.available_kit_names()", source)

    def test_removed_low_level_operations_are_not_package_root_exports(self) -> None:
        for name in (
            "available_kit_profiles",
            "clear_registry_cache",
            "detect_kits",
            "get_kit_profile",
            "read_genotypes_table",
            "render_genemapper_epg",
            "render_sample_svg",
            "resolve_kit",
            "write_svg",
        ):
            with self.subTest(name=name):
                self.assertFalse(hasattr(epg_renderer, name))


class ImmutableCallModelTests(unittest.TestCase):
    def test_marker_call_defensively_copies_alleles(self) -> None:
        calls = [AlleleCall(1, "15", 100)]
        marker = MarkerCall("D3S1358", "FAM", calls)
        calls.append(AlleleCall(2, "16", 90))
        self.assertEqual(marker.alleles, (AlleleCall(1, "15", 100),))
        with self.assertRaises(FrozenInstanceError):
            marker.dye = "VIC"

    def test_sample_and_project_defensively_copy_nested_mappings(self) -> None:
        marker = MarkerCall("D3S1358", "FAM", (AlleleCall(1, "15", 100),))
        marker_builder = {"D3S1358": marker}
        sample = SampleCall("S1", marker_builder)
        marker_builder.clear()
        self.assertEqual(tuple(sample.markers), ("D3S1358",))
        with self.assertRaises(TypeError):
            sample.markers["vWA"] = marker

        sample_builder = {"S1": sample}
        project = GeneMapperProject(
            sample_builder,
            ("Sample Name", "Marker"),
            "\t",
            "Sample Name",
        )
        sample_builder.clear()
        self.assertEqual(project.sample_ids, ("S1",))
        with self.assertRaises(TypeError):
            project.samples["S2"] = sample

    def test_marker_call_no_longer_contains_unused_source_order(self) -> None:
        self.assertNotIn("source_order", {item.name for item in fields(MarkerCall)})

    def test_call_and_project_constructors_reject_invalid_states(self) -> None:
        valid_call = AlleleCall(1, "15", 100)
        valid_marker = MarkerCall("D3S1358", "FAM", (valid_call,))
        invalid_factories = (
            lambda: AlleleCall(0, "15", 100),
            lambda: AlleleCall(1, "   ", 100),
            lambda: AlleleCall(1, "15", -1),
            lambda: AlleleCall(1, "15", 100, size_bp="not-a-number"),
            lambda: AlleleCall(1, "15", 100, size_bp="NaN"),
            lambda: AlleleCall(1, "15", 100, area=-1),
            lambda: MarkerCall("", "FAM", (valid_call,)),
            lambda: MarkerCall(
                "D3S1358",
                "FAM",
                (AlleleCall(1, "15", 100), AlleleCall(1, "16", 90)),
            ),
            lambda: SampleCall("", {}),
            lambda: SampleCall("S", {"vWA": valid_marker}),
            lambda: GeneMapperProject(
                {"S2": SampleCall("S", {})},
                ("Sample Name",),
                "\t",
                "Sample Name",
            ),
            lambda: GeneMapperProject({}, (), "\t", "Sample Name"),
            lambda: GeneMapperProject({}, ("Sample Name",), "::", "Sample Name"),
            lambda: GeneMapperProject({}, ("Sample Name",), "\t", ""),
            lambda: GeneMapperProject(
                {}, ("Sample Name",), "\t", "Sample Name", export_mode="other"
            ),
        )
        for factory in invalid_factories:
            with self.subTest(factory=factory), self.assertRaises(ValueError):
                factory()

    def test_sample_call_requires_typed_origin_and_height_mode(self) -> None:
        with self.assertRaisesRegex(TypeError, "ProfileOrigin"):
            SampleCall("S", {}, origin="manual")  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "PeakHeightMode"):
            SampleCall("S", {}, height_mode="uniform")  # type: ignore[arg-type]

        sample = SampleCall(
            "S",
            {},
            origin=ProfileOrigin.MANUAL,
            height_mode=PeakHeightMode.UNIFORM,
        )
        self.assertIs(sample.origin, ProfileOrigin.MANUAL)
        self.assertIs(sample.height_mode, PeakHeightMode.UNIFORM)

    def test_loaded_project_is_immutable_at_every_call_layer(self) -> None:
        project = load_project(FIXTURE)
        sample = project.sample("S1")
        marker = sample.markers["D3S1358"]
        with self.assertRaises(FrozenInstanceError):
            marker.marker = "vWA"
        with self.assertRaises(FrozenInstanceError):
            sample.sample_id = "S2"
        with self.assertRaises(FrozenInstanceError):
            project.delimiter = ","


class TypedMetadataTests(unittest.TestCase):
    def test_bundled_profiles_use_typed_metadata_and_retain_source_use(self) -> None:
        profile = load_kit("GlobalFiler")
        self.assertIsInstance(profile.kit_type, KitType)
        self.assertIsInstance(profile.export_compatibility, ExportCompatibility)
        self.assertTrue(profile.sources)
        self.assertTrue(all(isinstance(source, SourceReference) for source in profile.sources))
        self.assertTrue(all(source.use for source in profile.sources))
        self.assertTrue(
            all(isinstance(value, MarkerMetadata) for value in profile.marker_metadata.values())
        )
        self.assertTrue(
            all(
                isinstance(value.marker_type, MarkerType)
                for value in profile.marker_metadata.values()
            )
        )

    def test_metadata_constructors_reject_untyped_or_blank_values(self) -> None:
        with self.assertRaises(TypeError):
            MarkerMetadata("str")
        with self.assertRaises(ValueError):
            MarkerMetadata(MarkerType.STR, copy_group="   ")
        with self.assertRaises(TypeError):
            SourceReference(1, "use")
        with self.assertRaises(ValueError):
            SourceReference("Source", "   ")

    def test_kit_profile_rejects_untyped_or_inconsistent_metadata(self) -> None:
        profile = load_kit("GlobalFiler")
        invalid_cases = (
            ({"kit_type": "autosomal"}, TypeError),
            ({"export_compatibility": "genemapper"}, TypeError),
            ({"display_name": 1}, TypeError),
            ({"manufacturer": "   "}, ValueError),
            ({"coordinate_model": load_kit("NGM").coordinate_model}, ValueError),
            ({"channel_colors": {}}, ValueError),
            ({"dye_aliases": {"fam": "UNKNOWN"}}, ValueError),
            ({"marker_metadata": {"UNKNOWN": MarkerMetadata(MarkerType.STR)}}, ValueError),
        )
        for changes, error_type in invalid_cases:
            with self.subTest(changes=changes), self.assertRaises(error_type):
                replace(profile, **changes)

    def test_kit_profile_defensively_copies_public_mappings(self) -> None:
        profile = load_kit("GlobalFiler")
        colors = dict(profile.channel_colors)
        copied = replace(profile, channel_colors=colors)
        colors.clear()
        self.assertEqual(
            set(copied.channel_colors), {channel.code for channel in copied.kit.channels}
        )
        with self.assertRaises(TypeError):
            copied.channel_colors["FAM"] = "#000000"


class ImmutableResultTests(unittest.TestCase):
    def test_positioned_sample_defensively_copies_sequences(self) -> None:
        peaks: list = []
        issues: list = []
        sample = PositionedSample(
            sample_id="S",
            kit_name="GlobalFiler",
            coordinate_model_version="1",
            coordinate_kind=CoordinateKind.RANGE_CENTERED_NOMINAL,
            exact_bin_centres=False,
            peaks=peaks,
            issues=issues,
        )
        peaks.append(object())
        issues.append(object())
        self.assertEqual(sample.peaks, ())
        self.assertEqual(sample.issues, ())

    def test_kit_match_defensively_copies_diagnostic_sequences(self) -> None:
        match = match_kits(load_project(FIXTURE).sample("S1"))[0]
        missing = list(match.missing_markers)
        copied = replace(match, missing_markers=missing)
        missing.append("X")
        self.assertNotIn("X", copied.missing_markers)
        self.assertIsInstance(copied, KitMatch)
        self.assertIsInstance(copied.confidence, Confidence)

    def test_batch_results_use_typed_status_and_immutable_items(self) -> None:
        item = BatchRenderItem("S", None, BatchStatus.FAILED, "failed")
        items = [item]
        result = BatchRenderResult(
            Path("input.tsv"),
            Path("output"),
            None,
            OutputFormat.SVG,
            items,
            Path("output/manifest.json"),
        )
        items.clear()
        self.assertEqual(result.items, (item,))
        self.assertIs(result.items[0].status, BatchStatus.FAILED)
        with self.assertRaises(ValueError):
            BatchRenderItem("", None, BatchStatus.FAILED)
        with self.assertRaises(TypeError):
            BatchRenderItem("S", None, "error")
        with self.assertRaises(TypeError):
            BatchRenderResult(
                Path("input.tsv"),
                Path("output"),
                None,
                "svg",
                (),
                Path("output/manifest.json"),
            )

    def test_real_batch_manifest_serializes_enum_status_as_string(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = render_batch(FIXTURE, Path(directory) / "out", kit_name="GlobalFiler")
            self.assertIs(result.items[0].status, BatchStatus.SUCCEEDED)
            self.assertIn('"status": "ok"', result.manifest_path.read_text(encoding="utf-8"))


class ConstructorInvariantTests(unittest.TestCase):
    def test_kit_components_reject_invalid_construction(self) -> None:
        channel = DyeChannel("FAM", "Blue", "blue", 0)
        marker = MarkerDefinition("D3S1358", "FAM", 0, ("15",))
        invalid_factories = (
            lambda: DyeChannel("---", "Blue", "blue", 0),
            lambda: DyeChannel("FAM", "Blue", "blue", -1),
            lambda: MarkerDefinition("D3S1358", "FAM", -1, ("15",)),
            lambda: KitDefinition("Kit", "", (), (channel,), (marker,)),
            lambda: KitDefinition("Kit", "1", (), (), (marker,)),
            lambda: KitDefinition("Kit", "1", (), (channel,), ()),
            lambda: KitDefinition("Kit", "1", ("kit",), (channel,), (marker,)),
        )
        for factory in invalid_factories:
            with self.subTest(factory=factory), self.assertRaises(KitDefinitionError):
                factory()

    def test_kit_match_rejects_untyped_confidence_and_invalid_scores(self) -> None:
        kit = load_kit("GlobalFiler").kit
        with self.assertRaises(TypeError):
            KitMatch(kit, "exact", 1.0, 1.0, 1.0, (), (), ())
        with self.assertRaises(ValueError):
            KitMatch(kit, Confidence.EXACT, 1.1, 1.0, 1.0, (), (), ())
        with self.assertRaises(ValueError):
            KitMatch(kit, Confidence.EXACT, 1.0, 1.0, 1.0, (), (), (), True)
        with self.assertRaises(ValueError):
            KitMatch(kit, Confidence.EXACT, 1.0, 1.0, 1.0, (), (), (), -1)


if __name__ == "__main__":
    unittest.main()
