"""Regressions for the output-file suffix chosen in the GUI.

The GUI enforces the suffix of the selected output format. A dot inside a user-chosen
file name, such as ``run.v2`` or ``DNA-12.3``, is part of the name and must not be
replaced; only an existing image suffix is swapped for the selected one.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from epg_renderer.gui_workflow import validated_output_path


class GuiOutputSuffixTests(unittest.TestCase):
    def test_dot_in_file_name_is_kept_and_suffix_appended(self) -> None:
        self.assertEqual(validated_output_path("run.v2", "svg"), Path("run.v2.svg"))

    def test_sample_name_with_decimal_point_is_kept(self) -> None:
        self.assertEqual(validated_output_path("DNA-12.3", "png"), Path("DNA-12.3.png"))

    def test_existing_image_suffix_is_replaced_by_selected_format(self) -> None:
        self.assertEqual(validated_output_path("out.png", "svg"), Path("out.svg"))
        self.assertEqual(validated_output_path("out.JPEG", "jpeg"), Path("out.jpg"))

    def test_missing_suffix_is_appended(self) -> None:
        self.assertEqual(validated_output_path("out", "jpeg"), Path("out.jpg"))

    def test_format_switch_helper_keeps_dots_in_file_names(self) -> None:
        from epg_renderer.gui_workflow import output_path_with_suffix

        self.assertEqual(output_path_with_suffix("run.v2.svg", "jpeg"), Path("run.v2.jpg"))
        self.assertEqual(output_path_with_suffix("run.v2", "png"), Path("run.v2.png"))


if __name__ == "__main__":
    unittest.main()
