from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "examples") not in sys.path:
    sys.path.insert(0, str(ROOT / "examples"))

# These imports intentionally follow the local examples-directory bootstrap.
import update_examples  # noqa: E402

from epg_renderer import load_project, position_sample  # noqa: E402


class ExampleArtifactTests(unittest.TestCase):
    def test_example_registry_matches_committed_svg_names(self) -> None:
        self.assertEqual(
            tuple(spec.name for spec in update_examples.list_example_specs()),
            # Since 0.15.0.dev1 also the showcase for docs/READING_THE_FIGURE.md.
            (
                "globalfiler",
                "ngm",
                "esi17-two-person-mixture",
                "ngm-detect-five-person-mixture",
                "ngm-showcase",
            ),
        )
        self.assertEqual(
            tuple(Path(spec.target_path).name for spec in update_examples.list_example_specs()),
            (
                "globalfiler_example.svg",
                "ngm_example.svg",
                "esi17_two_person_mixture_example.svg",
                "ngm_detect_five_person_mixture_example.svg",
                "ngm_showcase_example.svg",
            ),
        )

    def test_readme_embeds_current_registered_example_svg(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        showcase = "examples/esi17_two_person_mixture_example.svg"
        published_showcase = (
            "https://raw.githubusercontent.com/rsivth/EPG-Renderer/main/" + showcase
        )
        self.assertIn("## Example output", readme)
        self.assertIn(
            f"![Synthetic two-person PowerPlex ESI 17 Fast electropherogram]({published_showcase})",
            readme,
        )
        registered = {spec.target_path for spec in update_examples.list_example_specs()}
        self.assertIn(showcase, registered)

    def test_ngm_detect_five_person_fixture_has_expected_dense_mixture_structure(self) -> None:
        fixture = ROOT / "tests/fixtures/ngm_detect_five_person_mixture.tsv"
        sample = load_project(fixture).sample("NGM_DETECT_5P_MIX")
        biological_counts = {
            name: len(call.alleles)
            for name, call in sample.markers.items()
            if name not in {"IQCS", "IQCL", "Yindel", "Amelogenin"}
        }
        self.assertEqual(max(biological_counts.values()), 10)
        self.assertGreaterEqual(
            sum(count == 10 for count in biological_counts.values()),
            8,
        )
        self.assertTrue(all(count <= 10 for count in biological_counts.values()))
        positioned = position_sample(sample, kit_name="NGM Detect")
        self.assertEqual(positioned.kit_name, "NGM Detect")
        self.assertGreater(len(positioned.peaks), 100)

    def test_committed_example_svgs_are_current(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory)
            for spec in update_examples.list_example_specs():
                with self.subTest(example=spec.name):
                    rendered = update_examples.render_example(
                        spec, root=ROOT, output_directory=output_directory
                    )
                    committed = ROOT / spec.target_path
                    self.assertEqual(
                        rendered.read_text(encoding="utf-8"),
                        committed.read_text(encoding="utf-8"),
                        msg=(
                            f"{committed.name} is outdated. Run: python examples/update_examples.py"
                        ),
                    )


if __name__ == "__main__":
    unittest.main()
