from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from epg_renderer.domain import PeakHeightMode
from epg_renderer.manual_gui import ManualProfileDialog
from epg_renderer.manual_profile import parse_manual_marker_text
from epg_renderer.models import AlleleCall
from epg_renderer.parser import NumericConversionError, read_genotypes_table


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


class RfuLimitTests(unittest.TestCase):
    def _write_export(self, height: int | str) -> Path:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".tsv") as temporary:
            path = Path(temporary.name)
        path.write_text(
            f"Sample Name\tMarker\tAllele 1\tHeight 1\nS\tD3S1358\t15\t{height}\n",
            encoding="utf-8",
        )
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def test_limit_is_centralized_as_32767_rfu(self) -> None:
        try:
            from epg_renderer.rfu import MAX_RFU
        except ModuleNotFoundError:
            self.fail("epg_renderer.rfu must define the shared RFU limit")
        self.assertEqual(MAX_RFU, 32_767)

    def test_genemapper_parser_accepts_supported_rfu_maximum(self) -> None:
        project = read_genotypes_table(self._write_export(32_767))
        call = project.sample("S").markers["D3S1358"].alleles[0]
        self.assertEqual(call.height, 32_767)

    def test_genemapper_parser_rejects_rfu_above_supported_maximum(self) -> None:
        with self.assertRaisesRegex(NumericConversionError, "32,767"):
            read_genotypes_table(self._write_export(32_768))

    def test_genemapper_parser_rejects_pathological_rfu_without_overflow(self) -> None:
        with self.assertRaisesRegex(NumericConversionError, "32,767"):
            read_genotypes_table(self._write_export("9" * 400))

    def test_manual_parser_accepts_supported_rfu_maximum(self) -> None:
        entry = parse_manual_marker_text(
            "D3S1358",
            "15",
            "32767",
            PeakHeightMode.RFU,
        )
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.heights, (32_767,))

    def test_model_rejects_rfu_above_supported_maximum(self) -> None:
        with self.assertRaisesRegex(ValueError, "32,767"):
            AlleleCall(1, "15", 32_768)

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
