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

Run the complete functional test suite:

```bash
python -m tools.run_all_tests
```

Run it from the repository root with `-m`; starting `tools/run_all_tests.py` by path
cannot import the `tools` package. Tests that need Tkinter belong in `test_gui*.py`
modules; every other test module must import without Tkinter.

Run linting, formatting verification, strict MyPy, and compilation:

```bash
python -m tools.run_quality_checks
```

Run tests with enforced line and branch coverage:

```bash
python -m tools.run_coverage_checks
```

Before committing a release candidate, run the aggregate release gate:

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

Only the wheel and standard source distribution belong on PyPI. The complete source
ZIP, its checksum, and standalone Windows deliverables remain GitHub Release assets.

## Versions

Published releases use `X.Y.Z`. Every change between two releases is delivered as a
development version `X.Y.Z.devN` of the next release, for example `0.14.0.dev1`,
`0.14.0.dev2`, and then `0.14.0`. `pip` never prefers a development version over a
release. Keep `pyproject.toml` and `src/epg_renderer/version.py` identical, record
changes under `## Unreleased` in `CHANGELOG.md`, and rename that section to the
version when it is released.

Windows file-version metadata holds four numbers, so `X.Y.Z.devN` and `X.Y.ZrcN` map
to `X.Y.Z.0`; the full version remains visible as the product version. The Windows
binary smoke test accepts the same three formats.

## CI contract

Normal CI exercises Python 3.10 through 3.14 on Linux, Windows, and macOS. Release
preflight repeats on all three platforms after the complete test matrix succeeds.

Both workflows pin every external action to a full commit with its release tag as a
comment, and use the same commit for the same action. Update an action in
`ci.yml` and `publish-pypi.yml` together.

The dedicated Windows binary job:

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

## TestPyPI and PyPI publication

Publication uses `.github/workflows/publish-pypi.yml` and PyPI Trusted Publishing.
The build job has read-only repository access and no publishing identity. Only the two
small publish jobs receive `id-token: write`; no PyPI API token or password belongs in
GitHub secrets.

Before the first run:

1. enable two-factor authentication on the TestPyPI and PyPI maintainer accounts;
2. create GitHub environments named exactly `testpypi` and `pypi` and protect `pypi`
   with a required reviewer;
3. configure a pending Trusted Publisher separately on TestPyPI and PyPI with project
   name `epg-renderer`, owner `rsivth`, repository `EPG-Renderer`, workflow filename
   `publish-pypi.yml`, and the matching environment name;
4. confirm that the public maintainer identity in `pyproject.toml` is the identity that
   should appear in package metadata.

The normal release sequence is:

1. set an unused release-candidate version such as `X.Y.Zrc1` in both
   `pyproject.toml` and `src/epg_renderer/version.py`, update the changelog and
   generated examples, and merge only after the complete CI matrix is green;
2. manually run **Publish Python distributions** from the default branch; this builds
   and verifies the artifacts, publishes only to TestPyPI, downloads the indexed
   wheel, byte-compares it with the build artifact, and smoke-tests it;
3. inspect the TestPyPI project description, links, metadata, and installation in a
   normal user environment;
4. prepare the unused final version `X.Y.Z`, repeat the checks, and push the exact tag
   `vX.Y.Z`; a mismatched tag is rejected before any upload;
5. the tag workflow first validates the final artifacts through TestPyPI again, then
   waits at the protected `pypi` environment before publishing the same wheel and
   source distribution to PyPI;
6. create the corresponding GitHub Release and attach the verified complete source
   ZIP, checksums, and any verified platform binaries.

PyPI and TestPyPI versions are immutable. Do not reuse a version, enable
`skip-existing`, delete and recreate a release, or upload a locally rebuilt
replacement. Correct a failed candidate with a new release-candidate number. See the
[PyPI Trusted Publishing guide](https://docs.pypi.org/trusted-publishers/) for account
and pending-publisher setup.

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
tests where representative exports are available.

## Technical references

- [Architecture](ARCHITECTURE.md)
- [Source-code documentation policy](CODE_DOCUMENTATION.md)
- [Declarative kit format](KIT_FORMAT.md)
- [API reference](API.md)
- [Coordinate model](COORDINATE_MODEL.md)
- [Sources and provenance](SOURCES.md)

Return to the [documentation home](index.md).
