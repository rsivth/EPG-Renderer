from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from epg_renderer.cli import build_parser
from epg_renderer.gui_workflow import inspect_genemapper_file

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


class GuiWorkflowTests(unittest.TestCase):
    def test_globalfiler_fixture_is_unambiguously_resolved(self):
        result = inspect_genemapper_file(FIXTURES / "globalfiler_minimal.tsv")
        decision = result.sample("S1")
        self.assertEqual(decision.resolved_kit_name, "GlobalFiler")
        self.assertFalse(decision.requires_user_selection)

    def test_ambiguous_sparse_esi_esx_file_requires_selection(self):
        text = "Sample Name\tMarker\tDye\tAllele 1\tHeight 1\n"
        rows = [
            ("S", "Amelogenin", "FL", "X", "500"),
            ("S", "D3S1358", "FL", "15", "700"),
            ("S", "vWA", "TMR", "16", "600"),
            ("S", "SE33", "CXR", "20", "400"),
        ]
        text += "".join("\t".join(row) + "\n" for row in rows)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ambiguous.tsv"
            path.write_text(text, encoding="utf-8")
            decision = inspect_genemapper_file(path).sample("S")
        self.assertTrue(decision.requires_user_selection)
        self.assertIsNone(decision.resolved_kit_name)
        self.assertIn("PowerPlex ESI 17 Fast", decision.compatible_kit_names)
        self.assertIn("PowerPlex ESX 17 Fast", decision.compatible_kit_names)

    def test_gui_module_imports_without_creating_a_window(self):
        import epg_renderer.gui as gui

        self.assertTrue(callable(gui.main))
        self.assertTrue(hasattr(gui, "EpgRendererApp"))

    def test_gui_check_builds_and_closes_a_hidden_application(self):
        import epg_renderer.gui as gui

        root = mock.Mock()
        with (
            mock.patch.object(gui, "available_kit_profiles", return_value=(object(),)),
            mock.patch.object(gui.tk, "Tk", return_value=root),
            mock.patch.object(gui, "EpgRendererApp") as application,
        ):
            status = gui.main(["--check"])

        self.assertEqual(status, 0)
        root.withdraw.assert_called_once_with()
        application.assert_called_once_with(root)
        root.update_idletasks.assert_called_once_with()
        root.destroy.assert_called_once_with()

    def test_gui_rejects_unknown_noninteractive_arguments(self):
        import epg_renderer.gui as gui

        with mock.patch.object(gui.tk, "Tk") as root:
            status = gui.main(["--unknown"])
        self.assertEqual(status, 2)
        root.assert_not_called()


class GuiCommandLineTests(unittest.TestCase):
    def test_cli_exposes_yellow_channel_choice(self):
        parser = build_parser()
        args = parser.parse_args(["in.csv", "out.svg", "--yellow-channel", "black"])
        self.assertEqual(args.yellow_channel, "black")

    def test_pyproject_contains_gui_entry_point(self):
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('epg-render-gui = "epg_renderer.gui:main"', text)


if __name__ == "__main__":
    unittest.main()


class GuiWorkflowBoundaryTests(unittest.TestCase):
    def test_file_inspection_rejects_unknown_sample(self):
        inspection = inspect_genemapper_file(FIXTURES / "globalfiler_minimal.tsv")
        with self.assertRaises(KeyError):
            inspection.sample("missing")

    def test_custom_sample_column_is_supported(self):
        text = "ID\tMarker\tDye\tAllele 1\tHeight 1\nX\tD3S1358\tB\t15\t100\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "custom.tsv"
            path.write_text(text, encoding="utf-8")
            inspection = inspect_genemapper_file(path, sample_id_column="ID")
        self.assertEqual(inspection.project.sample_ids, ("X",))

    def test_output_path_helpers_cover_jpeg_invalid_and_directory_paths(self):
        from epg_renderer.gui_workflow import suggested_output_path, validated_output_path

        suggestion = suggested_output_path("input.tsv", "A/B", "jpeg")
        self.assertEqual(suggestion.name, "A_B_epg.jpg")
        with self.assertRaises(ValueError):
            suggested_output_path("input.tsv", "S", "pdf")
        with (
            tempfile.TemporaryDirectory() as directory,
            self.assertRaises(ValueError),
        ):
            validated_output_path(directory, "svg")
