"""Contracts for where the graphical interface proposes to write an image."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from epg_renderer.gui_workflow import (
    default_output_directory,
    suggested_manual_output_path,
    suggested_output_path,
)


class DefaultOutputDirectoryTests(unittest.TestCase):
    """Never propose the process working directory, which depends on how the app started."""

    def test_the_documents_folder_is_preferred(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            documents = Path(home) / "Documents"
            documents.mkdir()
            with mock.patch.object(Path, "home", return_value=Path(home)):
                self.assertEqual(default_output_directory(), documents)

    def test_the_home_folder_is_the_fallback_without_a_documents_folder(self) -> None:
        with (
            tempfile.TemporaryDirectory() as home,
            mock.patch.object(Path, "home", return_value=Path(home)),
        ):
            self.assertEqual(default_output_directory(), Path(home))

    def test_a_file_that_is_not_a_directory_does_not_win(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            (Path(home) / "Documents").write_text("not a folder", encoding="utf-8")
            with mock.patch.object(Path, "home", return_value=Path(home)):
                self.assertEqual(default_output_directory(), Path(home))

    def test_the_working_directory_is_never_used(self) -> None:
        with tempfile.TemporaryDirectory() as workdir, tempfile.TemporaryDirectory() as home:
            (Path(home) / "Documents").mkdir()
            previous = Path.cwd()
            os.chdir(workdir)
            try:
                with mock.patch.object(Path, "home", return_value=Path(home)):
                    path = suggested_manual_output_path("Profile", "svg")
            finally:
                os.chdir(previous)
            self.assertNotEqual(path.parent, Path(workdir).resolve())
            self.assertEqual(path.parent, Path(home) / "Documents")


class ManualOutputPathTests(unittest.TestCase):
    """Keep manual profiles beside the data the user is working with."""

    def test_a_loaded_input_file_decides_the_folder(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "run.tsv"
            source.write_text("", encoding="utf-8")
            path = suggested_manual_output_path("Paper figure", "svg", input_path=source)
            self.assertEqual(path.parent, Path(directory))
            self.assertEqual(path.name, "Paper_figure_epg.svg")

    def test_an_explicit_directory_still_wins(self) -> None:
        path = suggested_manual_output_path("Figure 1 / teaching", "jpeg", directory="output")
        self.assertEqual(path, Path("output") / "Figure_1___teaching_epg.jpg")

    def test_the_genemapper_suggestion_stays_beside_its_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "run.tsv"
            path = suggested_output_path(source, "S1", "svg")
            self.assertEqual(path, Path(directory) / "S1_epg.svg")


if __name__ == "__main__":
    unittest.main()
