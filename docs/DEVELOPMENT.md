# Development and release checks

This guide describes the canonical development commands and release gates. Technical
architecture and kit-schema details remain in their dedicated documents.

## Development installation

Use Python 3.10 or newer. Install the project with development and raster dependencies:

```bash
python -m pip install -e ".[dev,raster]"
```

An isolated Python environment is recommended but not required by the repository. Use
the same intended interpreter consistently for installation and checks.

## Canonical checks

Before every push, run what CI checks, in one command:

```bash
python -m tools.run_release_checks --skip-build
```

It runs the quality checks and then the complete test suite under coverage, stops at
the first failing stage, and always ends with one summary of all stages, including
the test counts and `Result: PASSED` or `Result: FAILED`. That last block is the
answer; the output above it belongs to the individual stages.

Every check tool prints the same kind of short report: a framed block that ends with
`Result: PASSED` or `Result: FAILED`. Output of a failing tool appears above its
block, failing and skipped tests below it, and nothing else is printed when a check
passes. The tools can also be run one by one.

Run the complete functional test suite:

```bash
python -m tools.run_all_tests        # short report
python -m tools.run_all_tests -v     # every test as it runs
```

Run it from the repository root with `-m`; starting `tools/run_all_tests.py` by path
cannot import the `tools` package. What a test prints is held back and appears only in
the report of a failing test. Tests that need Tkinter belong in `test_gui*.py`
modules; every other test module must import without Tkinter.

Run linting, formatting verification, strict MyPy, and compilation:

```bash
python -m tools.run_quality_checks
```

Run tests with enforced line and branch coverage:

```bash
python -m tools.run_coverage_checks      # coverage table only if a threshold is missed
python -m tools.run_coverage_checks -v   # always the full coverage table
```

Before tagging a release, run the aggregate release gate:

```bash
python -m tools.run_release_checks
```

The release gate performs the quality and coverage checks, deterministic builds of
the complete source ZIP, standard source distribution (`.tar.gz`), and wheel,
extracted-source testing, strict Twine metadata/README validation, and isolated
installation smoke tests for both Python distribution formats. Every artifact is
built twice and must be byte-identical. A local green result does not replace the
operating-system and Python-version CI matrix.

To retain the exact fully verified artifacts instead of using a temporary directory:

```bash
python -m tools.run_release_checks --output-dir release
```

The release workflow attaches the complete source ZIP and the wheel to the GitHub
Release. The standard source distribution is built and checked but not published.

## Versions

Published releases use `X.Y.Z`. Every change between two releases is delivered as a
development version `X.Y.Z.devN` of the next release, for example `0.14.0.dev1`,
`0.14.0.dev2`, and then `0.14.0`. `pip` never prefers a development version over a
release. Keep `pyproject.toml` and `src/epg_renderer/version.py` identical, record
changes under `## Unreleased` in `CHANGELOG.md`, and rename that section to the
version when it is released. That section becomes the GitHub release text: write it
for users and do not cite development versions; the Git history keeps them.

Windows file-version metadata holds four numbers, so `X.Y.Z.devN` and `X.Y.ZrcN` map
to `X.Y.Z.0`; the full version remains visible as the product version. The Windows
binary smoke test accepts the same three formats.

## CI contract

Normal CI exercises Python 3.10 through 3.14 on Linux, Windows, and macOS. Release
preflight repeats on all three platforms after the complete test matrix succeeds.

All workflows pin every external action to a full commit with its release tag as a
comment, and use the same commit for the same action. Update an action in every
workflow file together.

The Windows binary job lives in `windows-binaries.yml` and is called by both `ci.yml`
and `release.yml`. It:

1. builds the stable `epg-render.exe` CLI and versioned GUI ZIP on a native runner;
2. extracts the exact GUI ZIP;
3. copies both deliverables outside their build tree;
4. removes Python and native-library environment assistance;
5. verifies version, help, kit resources, SVG, JPEG, batch rendering, GUI startup
   dependencies, and isolated runtime;
6. uploads only the verified deliverables.

An automated smoke test cannot cover SmartScreen, antivirus policy, or interactive
behavior on an ordinary user workstation. That downloaded-artifact check remains a
separate release gate.

## GitHub release

Releases are published only on GitHub; PyPI publication is deferred. The workflow
`release.yml` needs no secrets: only its final job may write to the repository.

Dry run: start **Release** manually from the default branch. It runs the release gate
and the Windows build, and uploads the exact assets plus the notes from
`## Unreleased` as the artifact `release-preview`. Nothing is published.

Release:

1. set the version `X.Y.Z` in `pyproject.toml` and `src/epg_renderer/version.py`,
   rename `## Unreleased` in `CHANGELOG.md` to `## X.Y.Z - YYYY-MM-DD`, regenerate the
   examples, and wait for a green CI run;
2. push the tag `vX.Y.Z`; a tag that does not match the version is rejected;
3. the workflow builds and verifies everything again and creates the GitHub Release
   with the GUI ZIP, `epg-render.exe`, the source ZIP, the wheel and `SHA256SUMS.txt`;
   the changelog section becomes the release text;
4. continue with `X.Y.(Z+1).dev1` and a new `## Unreleased` section.

A missing changelog section or release asset stops the workflow before anything is
published. Do not move or reuse a published tag; correct a release with a new version.

## Documentation checks

Documentation is release source and is regression-tested. When changing it:

- keep `README.md` as the concise project entry point;
- route detailed material through `docs/index.md`;
- use unversioned documentation filenames;
- keep relative Markdown links valid;
- avoid hard-coded current release numbers in evergreen instructions;
- preserve the explicit distinction between measured, nominal, estimated, and exact
  coordinates;
- run `tests/test_documentation_site.py` and the complete release gate.

The source-tree inventory test must be updated deliberately when a canonical
documentation page is added or removed. This prevents stale copies and accidental
versioned duplicates from entering release archives.

## Bundled STRio

GeneMapper exports are read by [STRio](https://github.com/rsivth/strio). EPG-Renderer
has no runtime dependencies and must run from an unpacked source ZIP and as a Windows
program without network access, so it carries an exact copy of one STRio release in
`src/epg_renderer/_vendor/strio/`. `src/epg_renderer/_vendor/VENDORED.json` records the
version, the release tag and the SHA-256 of every bundled file, and
`tests/test_strio_integration.py` fails on any difference. The copy is never edited by
hand; ruff and coverage skip it because STRio checks it in its own project.

To move to another STRio release:

```bash
git -C ../strio checkout vX.Y.Z
python -m tools.vendor_strio ../strio
python -m tools.run_all_tests
```

`python -m tools.vendor_strio ../strio --check` compares a checkout with the bundled
copy without changing anything. Record the STRio version in the changelog.

## Updating examples

Regenerate every committed example SVG with:

```bash
python examples/update_examples.py
```

The test suite compares regenerated SVG text with the committed files. Do not hand-edit
generated examples.

## Adding or changing kit profiles

Follow the [declarative kit format](KIT_FORMAT.md). New profiles require authoritative
source provenance plus schema, detection, positioning, rendering, and end-to-end input
tests. All test data is synthetic. Never commit a laboratory export; build a synthetic
export with the same column layout instead (see
[test data provenance](SOURCES.md#test-data-provenance)).

## Technical references

- [Architecture](ARCHITECTURE.md)
- [Source-code documentation policy](CODE_DOCUMENTATION.md)
- [Declarative kit format](KIT_FORMAT.md)
- [API reference](API.md)
- [Coordinate model](COORDINATE_MODEL.md)
- [Sources and provenance](SOURCES.md)

Return to the [documentation home](index.md).
