"""Regenerate the committed SVG examples from the bundled fixture inputs."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ExampleSpec:
    """One deterministic example-rendering job kept under version control."""

    name: str
    fixture_path: str
    target_path: str
    kit_name: str


EXAMPLE_SPECS: tuple[ExampleSpec, ...] = (
    ExampleSpec(
        name="globalfiler",
        fixture_path="tests/fixtures/globalfiler_minimal.tsv",
        target_path="examples/globalfiler_example.svg",
        kit_name="GlobalFiler",
    ),
    ExampleSpec(
        name="ngm",
        fixture_path="tests/fixtures/ngm_minimal.tsv",
        target_path="examples/ngm_example.svg",
        kit_name="NGM",
    ),
    ExampleSpec(
        name="esi17-two-person-mixture",
        fixture_path="tests/fixtures/esi17_two_person_mixture.tsv",
        target_path="examples/esi17_two_person_mixture_example.svg",
        kit_name="PowerPlex ESI 17 Fast",
    ),
    ExampleSpec(
        name="ngm-detect-five-person-mixture",
        fixture_path="tests/fixtures/ngm_detect_five_person_mixture.tsv",
        target_path="examples/ngm_detect_five_person_mixture_example.svg",
        kit_name="NGM Detect",
    ),
    ExampleSpec(
        name="esi17-three-person-mixture",
        fixture_path="tests/fixtures/esi17_three_person_mixture.tsv",
        target_path="examples/esi17_three_person_mixture_example.svg",
        kit_name="PowerPlex ESI 17 Fast",
    ),
    ExampleSpec(
        name="ngm-showcase",
        fixture_path="tests/fixtures/ngm_showcase.tsv",
        target_path="examples/ngm_showcase_example.svg",
        kit_name="NGM",
    ),
)


def project_root() -> Path:
    """Return the project root that contains `src`, `tests`, and `examples`."""

    return Path(__file__).resolve().parents[1]


def list_example_specs() -> tuple[ExampleSpec, ...]:
    """Return the committed example definitions in deterministic render order."""

    return EXAMPLE_SPECS


def get_example_spec(name: str) -> ExampleSpec:
    """Resolve one example definition by its stable short name."""

    normalized = name.strip().casefold()
    for spec in EXAMPLE_SPECS:
        if spec.name.casefold() == normalized:
            return spec
    available = ", ".join(spec.name for spec in EXAMPLE_SPECS)
    raise ValueError(f"Unknown example {name!r}. Available examples: {available}.")


def _load_render_file():
    root = project_root()
    source_root = root / "src"
    if str(source_root) not in sys.path:
        sys.path.insert(0, str(source_root))
    from epg_renderer import render_file

    return render_file


def render_example(
    spec: ExampleSpec,
    *,
    root: Path | None = None,
    output_directory: Path | None = None,
) -> Path:
    """Render one committed example either in place or into another directory."""

    root = project_root() if root is None else root
    render_file = _load_render_file()
    source = root / spec.fixture_path
    if output_directory is None:
        target = root / spec.target_path
    else:
        target = output_directory / Path(spec.target_path).name
        target.parent.mkdir(parents=True, exist_ok=True)
    render_file(source, target, kit_name=spec.kit_name)
    return target


def render_examples(
    names: tuple[str, ...] | None = None,
    *,
    root: Path | None = None,
    output_directory: Path | None = None,
) -> tuple[Path, ...]:
    """Render all committed examples or a selected subset in deterministic order."""

    specs = EXAMPLE_SPECS if names is None else tuple(get_example_spec(name) for name in names)
    return tuple(
        render_example(spec, root=root, output_directory=output_directory) for spec in specs
    )


def main() -> int:
    """Refresh committed example SVGs from their fixture inputs."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "names",
        nargs="*",
        help="Optional short names of examples to regenerate (default: all).",
    )
    args = parser.parse_args()
    names = tuple(args.names) if args.names else None
    for path in render_examples(names):
        print(path.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
