"""Contracts for output filenames that Windows refuses to create."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path, PureWindowsPath

from epg_renderer.batch import render_genemapper_batch, safe_output_stem

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "globalfiler_minimal.tsv"

# Device names Windows reserves for every directory, with or without a suffix.
RESERVED_DEVICE_NAMES = (
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
)


def _is_reserved(stem: str) -> bool:
    return PureWindowsPath(stem).stem.casefold() in {
        name.casefold() for name in RESERVED_DEVICE_NAMES
    }


class ReservedDeviceNameTests(unittest.TestCase):
    """Never build an output filename Windows cannot create."""

    def test_every_reserved_device_name_is_escaped(self) -> None:
        for name in RESERVED_DEVICE_NAMES:
            for spelling in (name, name.casefold(), f"  {name}  ", name.capitalize()):
                with self.subTest(sample=spelling):
                    stem = safe_output_stem(spelling)
                    self.assertFalse(_is_reserved(stem), f"{spelling!r} produced {stem!r}")

    def test_a_reserved_name_with_a_suffix_is_escaped_as_well(self) -> None:
        # Windows reserves CON.svg exactly like CON, so the leading segment counts.
        for spelling in ("CON.svg", "nul.txt", "LPT1.jpeg"):
            with self.subTest(sample=spelling):
                self.assertFalse(_is_reserved(safe_output_stem(spelling)))

    def test_an_escaped_name_still_identifies_its_sample(self) -> None:
        self.assertTrue(safe_output_stem("CON").casefold().startswith("con"))
        self.assertNotEqual(safe_output_stem("CON"), safe_output_stem("PRN"))

    def test_names_that_only_look_reserved_are_left_alone(self) -> None:
        for spelling in ("CONSOLE", "PRINTER", "COM", "COM10", "LPT", "NULL", "AUXILIARY"):
            with self.subTest(sample=spelling):
                self.assertEqual(safe_output_stem(spelling), spelling)

    def test_ordinary_names_keep_their_previous_result(self) -> None:
        self.assertEqual(safe_output_stem("S1"), "S1")
        self.assertEqual(safe_output_stem("A/B"), "A_B")
        self.assertEqual(safe_output_stem("  spaced  "), "spaced")
        self.assertEqual(safe_output_stem(".."), "sample")
        self.assertEqual(safe_output_stem("ä ö ü"), "ä_ö_ü")


class ReservedDeviceNameBatchTests(unittest.TestCase):
    """A batch run must not produce reserved filenames either."""

    def test_batch_renames_a_sample_called_con(self) -> None:
        lines = FIXTURE.read_text(encoding="utf-8").splitlines()
        header, body = lines[0], lines[1:]
        rows = [header]
        for name in ("CON", "PRN", "Sample_1"):
            for row in body:
                fields = row.split("\t")
                fields[0] = name
                rows.append("\t".join(fields))
        source = Path(tempfile.mkdtemp()) / "reserved.tsv"
        source.write_text("\n".join(rows) + "\n", encoding="utf-8")
        output_dir = Path(tempfile.mkdtemp()) / "out"

        result = render_genemapper_batch(source, output_dir, kit_name="GlobalFiler")

        self.assertEqual(result.failed, 0)
        produced = [item.output_path for item in result.items if item.output_path is not None]
        self.assertEqual(len(produced), 3)
        for path in produced:
            with self.subTest(path=path.name):
                self.assertFalse(_is_reserved(path.stem))
        self.assertIn("Sample_1.svg", [path.name for path in produced])


if __name__ == "__main__":
    unittest.main()
