"""Regressions for stale review hints in the main GUI window.

Until 0.15.0 the red review hints of the last created image were only cleared when the
next image was created. After loading another file, selecting another sample, entering
a manual profile or choosing another kit, the hints of the previous profile stayed
next to the new one. Since 0.15.1.dev1 every change of the data or the kit clears
them. The image format, the yellow-dye colour and the output file do not change what
the hints say, so the hints stay when only those are changed.

Since 0.15.1.dev2 the hints are part of the status field instead of a label of their
own, so these tests check the hint text and no longer the visibility of a widget.
"""

from __future__ import annotations

import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from epg_renderer import gui
from epg_renderer.domain import PeakHeightMode

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SHOWCASE = FIXTURES / "ngm_showcase.tsv"
MINIMAL = FIXTURES / "ngm_minimal.tsv"
STALE = ("vWA allele 25: hint of the previously rendered profile",)


class _Variable:
    def __init__(self, value: object = "") -> None:
        self.value = value

    def get(self) -> object:
        return self.value

    def set(self, value: object) -> None:
        self.value = value


class _Widget:
    """Stand-in for a Tk widget: records options."""

    def __init__(self) -> None:
        self.options: dict[str, object] = {}

    def configure(self, **options: object) -> None:
        self.options.update(options)

    def update_idletasks(self) -> None:
        pass


def _app_with_stale_hints() -> gui.EpgRendererApp:
    """Return the application logic without a window, showing hints of an old image."""

    app = object.__new__(gui.EpgRendererApp)
    app.root = _Widget()  # type: ignore[assignment]
    app.inspection = None
    app.manual_profile = None
    app.input_var = _Variable()  # type: ignore[assignment]
    app.sample_var = _Variable()  # type: ignore[assignment]
    app.kit_var = _Variable()  # type: ignore[assignment]
    app.format_var = _Variable("svg")  # type: ignore[assignment]
    app.yellow_var = _Variable("yellow")  # type: ignore[assignment]
    app.output_var = _Variable()  # type: ignore[assignment]
    app.open_var = _Variable(False)  # type: ignore[assignment]
    app.diagnostics_var = _Variable()  # type: ignore[assignment]
    app.status_var = _Variable()  # type: ignore[assignment]
    app._last_suggested_output = None
    for name in ("sample_combo", "kit_combo", "render_button", "manual_button"):
        setattr(app, name, _Widget())
    app._show_diagnostics(STALE)
    return app


def _load(app: gui.EpgRendererApp, path: Path) -> None:
    with (
        patch.object(gui.filedialog, "askopenfilename", return_value=str(path)),
        patch.object(gui.messagebox, "showerror"),
    ):
        app.choose_input()


class StaleDiagnosticsTests(unittest.TestCase):
    def assert_hints_cleared(self, app: gui.EpgRendererApp) -> None:
        self.assertEqual(app.diagnostics_var.get(), "")

    def assert_hints_kept(self, app: gui.EpgRendererApp) -> None:
        self.assertIn(STALE[0], app.diagnostics_var.get())

    def test_helper_starts_with_visible_hints(self) -> None:
        self.assert_hints_kept(_app_with_stale_hints())

    def test_loading_another_file_clears_the_hints(self) -> None:
        app = _app_with_stale_hints()
        _load(app, MINIMAL)
        self.assertIsNotNone(app.inspection)
        self.assert_hints_cleared(app)

    def test_rejected_file_clears_the_hints(self) -> None:
        app = _app_with_stale_hints()
        _load(app, FIXTURES / "does_not_exist.tsv")
        self.assertIsNone(app.inspection)
        self.assert_hints_cleared(app)

    def test_selecting_a_sample_clears_the_hints(self) -> None:
        app = _app_with_stale_hints()
        _load(app, SHOWCASE)
        app._show_diagnostics(STALE)
        app._on_sample_selected()
        self.assert_hints_cleared(app)

    def test_manual_profile_clears_the_hints(self) -> None:
        app = _app_with_stale_hints()
        profile = SimpleNamespace(name="Manual", kit_name="NGM", height_mode=PeakHeightMode.UNIFORM)
        with patch.object(gui, "show_manual_profile_dialog", return_value=profile):
            app.choose_manual_profile()
        self.assertIs(app.manual_profile, profile)
        self.assert_hints_cleared(app)

    def test_cancelled_manual_dialog_keeps_the_hints(self) -> None:
        app = _app_with_stale_hints()
        with patch.object(gui, "show_manual_profile_dialog", return_value=None):
            app.choose_manual_profile()
        self.assert_hints_kept(app)

    def test_cancelled_file_dialog_keeps_the_hints(self) -> None:
        app = _app_with_stale_hints()
        with patch.object(gui.filedialog, "askopenfilename", return_value=""):
            app.choose_input()
        self.assert_hints_kept(app)

    def test_selecting_a_kit_clears_the_hints(self) -> None:
        app = _app_with_stale_hints()
        app._on_kit_selected()
        self.assert_hints_cleared(app)

    def test_image_format_change_keeps_the_hints(self) -> None:
        app = _app_with_stale_hints()
        _load(app, SHOWCASE)
        app._show_diagnostics(STALE)
        app.format_var.set("png")
        app._update_output_suffix()
        self.assert_hints_kept(app)

    def test_kit_selection_is_connected_in_the_window(self) -> None:
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"No display for a Tk window: {exc}")
        try:
            root.withdraw()
            app = gui.EpgRendererApp(root)
            self.assertTrue(app.kit_combo.bind("<<ComboboxSelected>>"))
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
