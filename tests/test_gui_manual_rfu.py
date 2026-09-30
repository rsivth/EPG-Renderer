"""Tkinter-dependent RFU-limit regression for the manual-profile dialog."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from epg_renderer.domain import PeakHeightMode
from epg_renderer.manual_gui import ManualProfileDialog


class _TextVariable:
    def __init__(self, value: str) -> None:
        self.value = value

    def get(self) -> str:
        return self.value


class _Window:
    def __init__(self) -> None:
        self.destroyed = False

    def destroy(self) -> None:
        self.destroyed = True


class ManualGuiRfuLimitTests(unittest.TestCase):
    def test_manual_gui_reports_out_of_range_rfu_without_closing(self) -> None:
        window = _Window()
        dialog = SimpleNamespace(
            height_mode_var=_TextVariable(PeakHeightMode.RFU.value),
            kit_var=_TextVariable("GlobalFiler"),
            name_var=_TextVariable("Manual profile"),
            _allele_vars={"D3S1358": _TextVariable("15")},
            _height_vars={"D3S1358": _TextVariable("32768")},
            result=None,
            window=window,
        )
        with (
            patch("epg_renderer.manual_gui.editable_marker_names", return_value=("D3S1358",)),
            patch("epg_renderer.manual_gui.messagebox.showerror") as show_error,
        ):
            ManualProfileDialog._submit(dialog)  # type: ignore[arg-type]
        show_error.assert_called_once()
        self.assertIn("32,767", show_error.call_args.args[1])
        self.assertIsNone(dialog.result)
        self.assertFalse(window.destroyed)


if __name__ == "__main__":
    unittest.main()
