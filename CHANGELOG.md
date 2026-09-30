# Changelog

## Unreleased

- completed PyPI project metadata, public links, classifiers, license expression, and
  installation documentation
- added a byte-reproducible standard source distribution beside the existing complete
  source ZIP and wheel
- added strict distribution inventory, core-metadata, rendered-README, reproducibility,
  and clean-install smoke checks to the release gate
- added separate least-privilege Trusted Publishing jobs for TestPyPI and PyPI, exact
  tag/version validation, indexed-wheel byte comparison, and a protected live-release
  boundary

## 0.13.41 - 2026-09-30

- replaced three stacked strings in `render_svg`, of which Python kept only the first as
  docstring, with one docstring that documents both accepted sample types
- added a source-documentation regression that rejects bare string statements after a
  docstring

## 0.13.40 - 2026-09-30

- drew exactly one full-width baseline segment in channels without called peaks instead
  of two identical overlapping segments

## 0.13.39 - 2026-09-30

- added the root operation `render_file_report`, which renders like `render_file` and
  returns a `RenderReport` with parser warnings, positioning issues and
  `has_omitted_peaks`
- pointed the `render_file` docstring and the API/Python guides to the new operation

## 0.13.38 - 2026-09-30

- reported an unknown `--kit` value as a normal CLI error (exit status 2) instead of a
  Python traceback
- raised `UnknownKitError` from `get_kit_profile`; it remains a `KeyError` for existing
  callers, is also a `ValueError`, and prints its message without extra quotes

## 0.13.37 - 2026-09-30

- reported an exported `Size n` outside the selected kit's marker range as
  `MeasuredSizeOutsideRangeError` (a `PositionModelError` naming marker, allele, size
  and range) instead of a bare `ValueError`
- recorded such peaks in permissive mode as omitted with issue code
  `measured_size_outside_range` (CLI exit status 3)
- isolated the affected sample in strict batch runs instead of aborting the batch

## 0.13.36 - 2026-08-27

- bounded vertical bp grid lines by the RFU plotting area
- changed peak-contour endpoints from round to blunt caps so they stop at the baseline
- reduced peak-contour width from 2.1 px to 1.8 px for subtler emphasis over the 1.5 px baseline
- added focused SVG regressions for all three graphical contracts

## 0.13.35 - 2026-08-27

- displayed Amelogenin as `A...` and Y-indel as `Y...` in marker bands
- retained the existing 8.4 px fallback font size for both fixed abbreviations
- added focused NGM Detect regressions for the exact label text, font size and
  independently rendered width

## 0.13.34 - 2026-08-27

- added independent CairoSVG/Pillow geometry tests that measure rendered glyph pixels instead of reusing the production width estimator
- demonstrated and fixed a real overflow for supported marker names dominated by wide bold glyphs
- introduced a conservative bold-text estimate only for marker-band fitting while retaining the existing peak-label layout calculation
- removed the circular marker-fit assertions that treated the renderer's estimate as their expected result
- verified that the correction leaves all committed example labels, lane counts, panel heights and document dimensions unchanged
- documented the cross-platform property-based visual check and its separation from the dependency-free core runtime

## 0.13.33 - 2026-08-27

- removed the hidden `positions -> kit_registry` dependency that completed a logical import cycle through `kit_schema`
- made each coordinate model own its immutable kit definition, so marker aliases and parameterless validation no longer consult the global bundled-kit registry
- strengthened kit-profile consistency checks from matching names to matching complete immutable kit definitions
- retained `kit_name` as a derived read-only property while replacing the low-level coordinate-model constructor's redundant `kit_name` argument with `kit`
- added focused structural and behavioural regressions proving coordinate-model operations remain independent of registry state

## 0.13.32 - 2026-08-27

- made positioned peaks and samples reject blank identities, malformed coordinates, contradictory coordinate provenance, invalid RFUs, inconsistent height modes and duplicate marker/index pairs when constructed
- made positioning issues normalize their optional allele and require non-empty diagnostic fields
- made manual marker entries enforce one positive in-range RFU per allele and made manual profiles enforce non-empty, unique, correctly typed entries consistent with their selected height mode
- made batch items require status-consistent output/error payloads and batch results require typed items with unique sample identifiers
- retained kit membership, dye assignment, coordinate-model matching, allele lookup and filesystem checks at the operation boundaries that own the required context
- retained renderer validation as defense in depth while moving ordinary invalid-state rejection to the earliest public constructor boundary
- added focused constructor regressions covering normalization, collection copying, scalar bounds and cross-field contradictions

## 0.13.31 - 2026-08-26

- introduced one package-wide 32,767-RFU structural ceiling based on the documented Applied Biosystems 3500/3500xL and Promega Spectrum Compact signal ranges
- rejected out-of-domain RFU heights consistently in GeneMapper parsing, public call models, positioned-render validation and manual-profile construction
- kept imported zero-height values valid while retaining the existing positive-height requirement for manual entries
- made the allowed manual RFU range visible in the GUI and kept invalid submissions open with a concise range error
- documented the manufacturer sources, the 3500-series 32,000-RFU off-scale threshold and the distinction between structural validation and analytical quality control
- added focused boundary and GUI regressions for 32,767-RFU acceptance and 32,768-RFU rejection

## 0.13.30 - 2026-08-26

- made reused batch output directories fail closed by retiring files owned by the previous valid manifest before processing the new input
- removed stale outputs after sample failures, parser failures and sample-set changes while preserving unrelated files
- rejected malformed manifests and output filenames containing POSIX or Windows path traversal instead of deleting guessed paths
- added focused regression coverage for the batch-output lifecycle and safety boundary
- refreshed committed example SVG metadata for the new package version

## 0.13.29 - 2026-08-26

- preserved per-peak coordinate provenance as measured export size, nominal kit coordinate, repeat-based estimate, verified exact bin centre or unpositioned
- stopped labeling exported `Size n` measurements as nominal in SVG attributes, accessibility descriptions and disclaimers
- added neutral `data-coordinate-bp` plus source-specific SVG metadata and document-level provenance/count summaries, including explicit mixed-source reporting
- replaced the misleading positioned-peak `nominal_bp` field with the semantically neutral `coordinate_bp` field
- changed the horizontal axis unit from `nominal bp` to the source-neutral `bp`
- added focused regressions for measured, nominal, estimated and mixed coordinate sources
- refreshed committed example SVG metadata for the new package version

## 0.13.28 - 2026-08-25

- rejected supplied dye labels that the selected kit cannot recognize instead of silently treating them as absent dye evidence
- recorded a dedicated `unknown_dye` issue in permissive positioning while preserving the raw source label and rendering under the validated kit channel
- preserved the existing neutral handling of omitted dyes, valid dye-alias normalization and known-channel mismatch behavior
- added focused strict/permissive regression coverage and documented the distinction between missing and unrecognized source dyes
- made disposable release-test environments preserve POSIX interpreter runtime-library paths while retaining normal Windows environment creation
- expanded CI coverage to Python 3.10 through 3.14 on Linux, Windows and macOS, including the complete release preflight on every platform
- added regression protection for portable clean-environment construction and the full supported platform/version matrix
- refreshed committed example SVG metadata for the new package version

## 0.13.27 - 2026-08-25

- made the complete configured quality gate pass without weakening its Ruff, formatting, strict MyPy or compilation checks
- corrected the Ruff documentation scope so root scripts are checked while tests and examples retain their deliberate documentation exclusions
- added `launch_gui.py` to linting and compilation, with an explicit boundary justification for its final broad startup-error handler
- corrected the manual-profile dialog parent type to the actual Tk/Toplevel window contract accepted by Tkinter's transient-window API
- applied the pinned Ruff formatter and safe lint corrections consistently across all configured source, test, example and root-script targets
- added regression protection for launcher coverage and the absence of a blanket documentation-rule exclusion
- refreshed committed example SVG metadata for the new package version

## 0.13.26 - 2026-08-25

- restored reproducible source releases by explicitly including `.gitattributes` and the BSD 3-Clause `LICENSE` in the source inventory and generated checksum manifest
- treated the default `release/` output directory as generated content so completed artifacts cannot contaminate a subsequent release build
- added focused regression coverage for repository inventory selection, source-archive license metadata, repeated default-output builds and CI release orchestration
- added a dedicated CI release job that runs the complete static-quality, reproducibility, installation-smoke and coverage preflight after the platform test matrix
- refreshed committed example SVG metadata for the new package version

## 0.13.25 - 2026-08-22

- clarified the development/release-check hierarchy: `run_all_tests.py` is the normal development entry point and `run_release_checks.py` is the release orchestrator
- documented the distinct responsibilities of quality, coverage and extracted-source smoke checks instead of presenting them as interchangeable top-level commands
- added regression protection against copy-generated duplicate root check scripts such as `run_quality_checks_2.py` and `run_release_checks_2.py`; such files also remain rejected by the explicit release allowlist
- refreshed committed example SVG metadata for the new package version

## 0.13.24 - 2026-08-22

- changed the kit/manufacturer subtitle from muted grey to the same dark primary text tone used by the document title, while keeping its 11 px size and position unchanged
- kept the x/y-axis typography unchanged; the `nominal bp` axis unit already uses the shared 10 px axis-text metric
- extended the shared typography metrics with primary and secondary text colours so title/subtitle and axis text no longer depend on duplicated colour literals
- refreshed committed example SVGs to reflect the updated subtitle colour

## 0.13.23 - 2026-08-22

- increased the x-axis base-pair labels, y-axis RFU labels and axis-unit labels from 9 px to 10 px for improved readability and alignment with the RFU values inside allele labels
- deliberately kept the document title and kit/manufacturer subtitle unchanged, after confirming that the subtitle already reads optically smaller than the 10 px in-label RFU text despite its nominal 11 px size
- introduced a shared typography metrics structure so axis text and subtitle sizing are defined centrally instead of as scattered CSS literals
- refreshed the committed example SVGs so the bundled showcase output reflects the updated axis typography

## 0.13.22 - 2026-08-22

- increased the default STR marker-band label font size from 9.5 px to 11.5 px while keeping the marker-band height unchanged
- introduced shared marker-label metrics so rendering, width fitting, fallback sizing, truncation and marker-band geometry use one consistent source of truth
- deliberately omitted letter spacing to avoid unnecessary width pressure and additional truncation in narrow marker bands
- refreshed all committed example SVGs and added regression coverage for the new marker-label sizing and fit contract

## 0.13.21 - 2026-08-22

- increased the peak-label allele and RFU font sizes by 0.5 px each for improved small-size readability
- refined the central label-metric architecture so box heights, lane heights and text baselines are derived consistently from the same shared label-geometry parameters instead of relying on duplicated numeric assumptions
- refreshed the committed example SVGs so the bundled showcase output reflects the updated label sizing
- extended regression coverage around shared label metrics and dense downward-growing label layouts

## 0.13.20 - 2026-08-22

- added a synthetic five-person NGM Detect mixture dataset spanning the biological markers of the kit and the two NGM Detect quality-control markers
- constructed the dense mixture with up to ten called alleles at several autosomal STR loci to exercise realistic high-contributor label density
- added the corresponding committed SVG example and dedicated wrapper script, fully integrated into the central example regeneration and stale-artifact checks
- added regression coverage for the five-person fixture, including the ten-allele density bound and successful NGM Detect positioning/rendering

## 0.13.19 - 2026-08-22

- centralized peak-label font and box geometry so text measurement, collision allocation, channel-height validation and SVG rendering use one shared set of metrics
- moderately enlarged allele labels, RFU labels and their boxes while preserving unlimited downward lane growth for dense STR profiles
- corrected the minimum channel-height validation so it is derived from the actual lane geometry instead of a separate approximate formula
- strengthened dense-label regression coverage with a 14-allele marker stress case that verifies non-overlap, downward panel expansion and containment of every label box
- refreshed all committed example SVGs so the README showcase and bundled examples reflect the updated label design

## 0.13.18 - 2026-08-22

- increased the coloured peak-outline stroke width again by a small further step to improve clarity at small SVG display sizes
- kept text sizes, baseline rendering, connector lines and overall layout unchanged to preserve the narrowly scoped design iteration
- refreshed the committed example SVGs so the bundled showcase output reflects the updated peak-line weight
- updated the regression test to lock in the new expected coloured peak-outline stroke width

## 0.13.17 - 2026-08-22

- increased the stroke width of the coloured peak outlines moderately so EPGs remain clearer at smaller SVG display sizes
- deliberately left text sizes, label layout, connector strokes and baseline geometry unchanged for a narrowly scoped design iteration
- refreshed the committed example SVGs so the bundled showcase output reflects the updated peak-line weight
- added regression coverage for the expected coloured peak-outline stroke width

## 0.13.16 - 2026-08-22

- restored a visible README showcase by embedding the current synthetic PowerPlex ESI 17 Fast two-person example SVG near the top of the project page
- linked the showcase directly to the committed generated SVG so refreshing examples also refreshes the README rendering check
- added regression coverage requiring the README showcase to reference a registered committed example SVG

## 0.13.15 - 2026-08-22

- added a third committed SVG example: a synthetic two-person PowerPlex ESI 17 Fast mixture
- added the synthetic ESI 17 mixture fixture that deterministically drives the new example rendering
- extended the central `examples/update_examples.py` workflow and regression coverage so the new example is regenerated and checked automatically with the existing examples

## 0.13.4 - 2026-08-22

- added a central `examples/update_examples.py` utility that deterministically regenerates every committed example SVG from the bundled fixtures
- updated the dedicated example wrapper scripts to delegate to the central updater instead of duplicating example-render logic
- added regression coverage that re-renders the committed examples and fails with an explicit instruction when any example SVG is stale
- refreshed the committed example SVGs so their metadata and rendering match the current renderer version

## 0.13.3 - 2026-08-22

- Left-aligned dye-channel names from a fixed position inside the channel panel instead of right-aligning them against the RFU-label anchor.
- Added a fixed 10 px internal gap between the left channel border and every dye name so long labels such as `Fluorescein` remain inside the panel.
- Kept RFU labels, plot geometry, marker bands, peak positioning and all other rendering behavior unchanged.
- Added regression coverage for the general alignment/padding contract and the PowerPlex ESI 17 Fast long-label case.

## 0.13.2 - 2026-08-03

- Improved marker-label fitting so every marker name is checked against the actual band width before rendering.
- Preserved the normal marker-label size whenever the full name fits and retained the existing reduced fallback size for moderately narrow bands.
- Added a final truncation step with an ellipsis when even the reduced font size would overflow the marker band, preventing cases such as AMEL from protruding beyond short bands.
- Kept the full canonical marker name in the existing SVG metadata while shortening only the visible label text when necessary.
- Added focused regression tests for deterministic truncation and for keeping rendered marker labels within their marker-band width.
- Preserved all existing parser, manual-profile, GUI, CLI, batch and rendering behavior beyond the marker-label fit improvement.

## 0.13.0 - 2026-08-03

- Added a modal GUI workflow for constructing kit-aware profiles manually for paper, proposal and teaching figures.
- Added all 14 bundled kits to manual selection while excluding technical control markers from allele entry.
- Added unrestricted multi-peak marker entry with comma-, semicolon- or whitespace-separated allele values and strict kit-coordinate validation.
- Added separate RFU and uniform non-quantitative height modes; uniform profiles store no invented RFU values and omit RFU ticks, height labels and horizontal RFU grid lines.
- Added explicit profile-origin and peak-height-mode state throughout the shared sample, positioning, SVG metadata, accessibility text, subtitle and disclaimer pipeline.
- Added a dedicated manual-profile validation module and a separate Tkinter dialog module instead of duplicating kit or rendering logic in the GUI.
- Added manual SVG/PNG/JPEG workflow support and safe output-name suggestions without generating temporary GeneMapper files.
- Added 18 focused regression tests, including minimal manual rendering across every bundled kit, invalid input boundaries and quantitative/non-quantitative SVG semantics.
- Preserved all existing GeneMapper parser, CLI, batch and rendering behavior; the previous 413-test suite remains green.

## 0.12.4 - 2026-07-27

- Changed the default EPG title to show only the original sample display name rather than appending the canonical kit name.
- Preserved the original display name through the positioning model while retaining the unique internal sample ID in SVG metadata.
- Expanded the subtitle to show the full kit product name and manufacturer from the central validated kit profile, followed by the unchanged coordinate-model and called-peak information.
- Added regression tests for display-name handling, complete kit/manufacturer subtitles and metadata traceability.

## 0.12.3 - 2026-07-27

- Changed the off-ladder marker ribbon to a strong warm orange and updated the `OL` lettering to white bold text aligned to the stripe angle itself.
- Repositioned the diagonal ribbon inside the marker band so it crosses both the top and bottom edges while remaining visibly inset from the right end.
- Added adaptive narrow-marker safeguards so short bands such as AMEL keep the ribbon inside the marker area and can fall back to a textless stripe if a future kit becomes even narrower.
- Changed the marker-band background from white to a very light neutral grey to improve visual grouping without reintroducing a tinted channel background.
- Added `START_GUI.vbs` as the primary console-free Windows launcher; it uses absolute paths and does not assign a UNC folder as a CMD working directory.
- Renamed the former batch entry point to `START_GUI_CMD_FALLBACK.bat` to avoid ambiguity when Windows hides file extensions.
- Added graphical geometry, colour, short-marker, silent-launcher, UNC-path and release-allowlist regression checks.

## 0.12.1 - 2026-07-27

- Replaced the inline `OL` marker badge with a diagonal magenta/violet corner ribbon inspired by the GeneMapper artefact annotation look.
- Added a footer legend that explains each affected marker with the message `Marker [name] contains unpositioned off-ladder allele(s) without size information.`
- Extended SVG metadata with marker-annotation legend messages and regression tests for the new ribbon and legend rendering.

## 0.12.0 - 2026-07-27

- Off-ladder allele calls labelled `OL` without exported size information no longer block rendering.
- Such calls are preserved as marker-linked evidence and rendered as marker-level `OL` badges instead of synthetic peak positions.
- Strict positioning still rejects other non-positionable alleles by default; only the explicit `OL`-without-size case is downgraded to a non-fatal issue.
- SVG metadata now records marker-level annotation counts, and regression tests cover positioning, rendering, and omission boundaries.

## 0.11.2 - 2026-07-27

- Rounded every automatically chosen RFU axis maximum up to a readable value instead of using raw maxima such as 1397.
- Applied the same rounded-axis logic to per-channel scaling and global scaling so peaks remain visible while the top tick stays clean.
- Kept the existing three RFU labels per channel and made the intermediate label a simple fraction of the rounded maximum.
- Added regression tests for rounded per-channel RFU axes and updated the design tests to validate scaled rendering against rounded limits.

## 0.11.1 - 2026-07-27

- Changed the background of every dye-channel panel from off-white to pure white while preserving the existing panel outline, grid and rendering geometry.
- Added a regression test that fixes the channel-panel background and border colors.

## 0.11.0 - 2026-07-22

- Rebuilt GeneMapper ingestion around configurable scalar columns and indexed peak families instead of one fixed CSV layout.
- Accepted variable `Allele n`, `Height n`, `Size n`, `Area n`, `Mutation n` and `Comment n` families while preserving their numeric association and sparse indexes.
- Made exported dye information optional and retained it as evidence when present; selected kit profiles provide channel assignment when it is absent.
- Safely ignored empty unnamed trailing export columns while continuing to reject unnamed interior columns and unnamed columns containing data.
- Separated stable source-injection identity from the human-readable sample name, preventing duplicate sample names from being merged across files or runs.
- Preserved alleles without RFU when permissive parsing is requested and used exported fragment size directly when available.
- Added explicit allele-display-overflow and possible-width-truncation diagnostics.
- Added bounded repeat-based positioning for numeric off-ladder alleles while retaining strict handling of unpositionable labels.
- Added and validated separate NGM SElect and Investigator ESSplex SE QS kit profiles, including SE33 and the ESSplex quality sensors.
- Added both supplied complete mixed-stain exports as immutable end-to-end fixtures covering 39 injections, 677 marker rows and 2,678 exported peaks.

## 0.10.7 - 2026-07-22

- Added `START_GUI.bat` for direct offline Windows startup without package installation.
- Added `launch_gui.py`, which loads the bundled `src` tree and reports startup failures clearly.
- The launcher uses `pushd`, so UNC network paths are supported.
- Added launcher regression tests and release-allowlist coverage.

## 0.10.6 - 2026-07-22

- Made Pillow and CairoSVG genuinely optional for the test suite: CLI and raster test modules now import safely without either package, and only integration tests that require raster output are skipped.
- Added a complete minimal-dependency test run in a clean virtual environment containing neither Pillow nor CairoSVG.
- Added a separate raster-enabled installation and full test run using the published `raster` extra.
- Extended the release gate to verify minimal SVG-only operation and optional PNG/JPEG support independently.
- Documented the expected skipped-test behavior for minimal installations.

## 0.10.5

- Simplified the release gate so the complete test suite runs once under branch coverage instead of being repeated before and after coverage collection.
- Added separately enforced package and module line/branch coverage thresholds, including direct CLI and headless GUI workflow coverage.
- Added concise CLI handling for expected input, validation and rendering errors with exit status 2 and no traceback.
- Replaced the full extracted-source test rerun with a focused import, bundled-kit and SVG smoke test.
- Switched wheel construction to isolated PEP 517 builds with exactly pinned build and development tools.
- Replaced release exclusion-only selection with an explicit source allowlist; unknown files abort release construction.
- Added a Linux/Windows CI matrix for Python 3.10 through 3.13.
- Added visible phase reporting to the combined release gate.

## 0.10.5 - 2026-07-21

- Added complete docstrings for every public module, class, function and method in the production package.
- Rewrote source documentation around current contracts, scientific assumptions, units, nominal-coordinate limitations and error boundaries.
- Added structural protocols with explicit dependency contracts for CairoSVG and Pillow.
- Enabled Ruff pydocstyle rules as a permanent release quality gate while excluding only magic-method and layout-only conventions that add no useful information.
- Added regression tests that reject stale version-history, legacy-compatibility and test-oriented commentary in production modules.
- Added a concise source-code documentation policy and linked it from the project documentation index.
- Preserved all parser, positioning, rendering and output behavior; generated SVG geometry is unchanged apart from version metadata.

## 0.10.2 - 2026-07-21

- Reduced the package-root API to eight canonical operations plus `__version__`; data types, options, errors and lower-level helpers now live only in explicit subject modules.
- Made parsed projects, samples, marker mappings, kit metadata, kit-match diagnostics, positioned samples and batch results defensively immutable.
- Removed the unused marker `source_order` field and derived order exclusively from insertion-preserving immutable mappings.
- Replaced free-string kit, export, marker and batch states with typed enums and retained complete typed source references including their stated use.
- Moved validation into public model constructors so malformed identifiers, contradictory mapping keys, invalid enum values and inconsistent result metadata cannot produce exposed objects.
- Added focused API-surface and invariant tests and raised release coverage requirements for the public API, domain metadata and immutable model modules.

## 0.10.1

- Removed compatibility-only modules, alias APIs, dynamic kit constants and implicit GlobalFiler defaults.
- Consolidated all bundled kit profiles on the single supported JSON schema 1.1.
- Replaced version-bound regression files and supersession bookkeeping with a current thematic test suite and normal discovery.
- Removed historical requirement documents, baseline hashes, screenshots and versioned examples from the current source release.
- Replaced them with current API, architecture, coordinate, kit-format and provenance documentation plus two unversioned examples.
- Extended Ruff quality gates to the current test suite.

## 0.10.0 - 2026-07-21

- Preserved valid quoted multiline fields in GeneMapper CSV/TSV input instead of collapsing their embedded line breaks.
- Rejected malformed CSV quoting, quotes inside unquoted fields, unknown codec names and semantically duplicate indexed columns before row construction.
- Required coordinate-method payloads to use disjoint, method-specific fields in both runtime validation and the published JSON schemas.
- Allowed exact-bin-centre metadata only when every marker uses explicit allele coordinates.
- Rejected kit, channel and marker lookup names or aliases that normalize to an empty identifier.
- Required `marker_type` and `is_control` to agree and enforced bidirectional consistency between marker linkage metadata and declared linkage groups.
- Added focused v0.10.0 correctness and release regression tests while preserving the existing rendering geometry.

## 0.9.5 - 2026-07-21

- Replaced the fragile version-by-version test loader with complete `test*.py` discovery; every discovered test is now either executed automatically or excluded by exact ID with a documented supersession reason.
- Added stale-exclusion and duplicate-test-ID checks so new tests cannot be silently omitted and obsolete policy entries cannot accumulate.
- Added branch-aware coverage collection with enforced module-specific line-coverage thresholds for parser, registry, kit workflow, positioning, batch, rendering I/O/layout/options/SVG and headless GUI workflow logic.
- Added deterministic source-archive generation with normalized ZIP timestamps, ordering, permissions and an internal SHA-256 manifest.
- Added clean, reproducible wheel builds performed twice from independent staged source trees and compared byte-for-byte.
- Added source-archive cleanliness checks, a complete test run from the extracted archive, wheel-content inspection, isolated virtual-environment installation, CLI SVG generation, kit-resource loading and `pip check`.
- Added `run_release_checks.py` as the complete release gate and `build_release.py` as the canonical publication command.
- Excluded generated reports, build directories, caches, bytecode and egg metadata from canonical source releases while retaining required historical regression baselines and examples.

## 0.9.4 - 2026-07-21

- Added reproducible Ruff lint/format configuration and strict MyPy checking for the complete `epg_renderer` package.
- Added the `dev` optional dependency group and `run_quality_checks.py` release gate for linting, formatting, typing and compilation.
- Removed dead imports, modernized Python 3.10 type syntax, sorted public exports and added strict `zip` length checks where paired sequences must match.
- Replaced untyped parser keyword dictionaries with explicit calls and added typed protocols for batch callbacks and optional raster-library boundaries.
- Limited broad exception handling to deliberate process boundaries; GUI paths now distinguish expected user/data errors from logged unexpected internal failures.
- Wrapped output-directory creation failures in renderer-specific exceptions and verified that CairoSVG returns actual PNG bytes.
- Strengthened kit-schema object validation by rejecting non-string mapping keys supplied through the programmatic API.
- Preserved rendered GlobalFiler geometry exactly; current output differs from v0.9.3 only in release metadata.

## 0.9.3 - 2026-07-21

- Split the former monolithic renderer into focused option, layout, SVG, output and batch modules while retaining `epg_renderer.renderer` as the stable public facade.
- Replaced the 13-argument channel-rendering function with one immutable rendering-context object and removed unused label-collision state.
- Separated bundled kit-resource discovery/caching from kit payload construction and semantic validation.
- Preserved the established public API, batch patch boundary, kit behavior and GlobalFiler SVG geometry; the current SVG differs from v0.9.1 only by release metadata.
- Fixed a confirmed counter bug that reported every omitted unpositioned peak twice when `UnpositionedPolicy.OMIT` was selected.
- Hardened kit-schema semantics by rejecting canonically duplicate explicit allele positions, canonically duplicate linkage-group markers and blank optional marker-group values.
- Added 16 Phase-3 architecture, delegation, output-equivalence, schema-robustness, omitted-peak and release regression tests.

## 0.9.1 - 2026-07-21

- Consolidated all kit definitions, marker aliases, dye normalization and coordinate models onto the JSON-backed registry as the single active data source.
- Removed the hard-coded GlobalFiler kit definition, the duplicate legacy GlobalFiler coordinate resource and the renderer's GlobalFiler-specific positioning branch.
- Unified the legacy and registry coordinate-model classes while retaining the established GlobalFiler coordinate-model identifier `0.2` and all nominal coordinates.
- Converted `get_kit`, `get_coordinate_model`, `detect_kits`, `resolve_kit`, `position_sample` and related historical names into registry-backed compatibility entry points.
- Added precomputed marker lookup maps to `KitDefinition` so canonical marker and alias resolution is shared and constant-time.
- Added v0.9.1 equivalence, architecture, release-artifact and unchanged-scope regression tests.

## 0.9.0 - 2026-07-21

- Made batch rendering isolate sample-level kit, positioning and output failures; valid samples continue when requested, and fail-fast mode writes a partial manifest before re-raising the original error.
- Rejected duplicate marker rows after case/whitespace normalization and duplicate source aliases that resolve to the same canonical kit marker.
- Restricted GeneMapper GUI, CLI and high-level rendering workflows to kit profiles whose GeneMapper export compatibility is explicitly verified.
- Ensured GUI kit choices are actually resolvable for the selected sample and no longer offer known-incompatible candidates.
- Updated automatic output filename suggestions when the selected sample changes while preserving manually chosen output paths; blank or directory-only output paths are rejected.
- Added focused v0.9 regression and release-integrity tests for all Phase-1 corrections.

## 0.8.3 - 2026-07-21

- Removed the baseline entirely beneath each peak footprint; the channel baseline now stops at the left peak foot and resumes at the right peak foot.
- Kept the open peak geometry introduced in v0.8 so peaks rise from a clean gap rather than from a black or colored base segment.
- Added targeted regression tests covering the deliberate baseline-gap rendering and current release artifacts.

## 0.8.0 - 2026-07-21

- Fixed the peak geometry so the channel-colored contour no longer redraws the baseline beneath the peak; the black baseline segment remains visibly continuous into the peak base.
- Fixed distorted `AMEL` marker labels by basing fit checks on the displayed label and preferring a slightly smaller font over glyph scaling.
- Kept batch rendering, CLI, GUI and kit registry behavior unchanged while extending tests and documentation to the new release.

## 0.5.0 - 2026-07-21

- Added GitHub-ready beginner documentation and a professional API reference.
- Added a command-line interface via `epg-render` and `python -m epg_renderer`.
- Added optional PNG and JPEG/JPG output using CairoSVG and Pillow while retaining SVG as the canonical rendering format.
- Added format selection by output suffix and atomic raster-file writing.
- Changed default per-channel RFU scaling so each channel's highest positive called peak reaches 100% of the signal height.
- Removed the literal term `RFU` from allele-label boxes; the second line now contains the numeric value only.
- Replaced fixed collision lanes with automatically expanding, collision-free label allocation.
- Added a dedicated connector layer painted before all labels so connectors remain visually behind white label boxes.
- Colored each channel baseline with the channel color.
- Changed peak polygons to white fill with channel-colored outlines.
- Added reproducible SVG, PNG and JPEG examples.
- Added 37 v0.5 tests; 228 unchanged predecessor behavioural tests pass.
- Executed the complete unchanged v0.4 release suite: exactly 10 obsolete test methods fail, and only because they assert requirements intentionally superseded by v0.5; all 228 unaffected methods pass.

## 0.4.0 - 2026-07-21

- Added a schema-validated, JSON-backed kit registry.
- Migrated GlobalFiler kit metadata, channel colors, markers, alleles and nominal coordinate definitions to one declarative kit JSON.
- Added AmpFlSTR NGM with 16 loci, four dye channels, manufacturer panel ranges and allelic-ladder alleles.
- Added kit-generic detection and positioning across the registered JSON kits.
- Retained the legacy GlobalFiler positioning API for backward compatibility while the renderer consumes the JSON registry.
- Standardized marker boxes to white fill, black outline and black text.
- Moved allele/RFU labels below the x-axis into white, black-outlined boxes with black connector lines.
- Added data-driven channel colors, including black NED and red PET display channels for NGM.
- Added deterministic GlobalFiler and NGM v0.4 example SVGs.
- Added 75 v0.4 tests while retaining 99 v0.2 and 64 applicable v0.3 behavioural regression tests.
- Verified the original v0.3 release suite independently: 168/168 tests passed.
- Replaced five predecessor assertions that were exclusively tied to the obsolete v0.3 version/metadata/example artifact; all other v0.3 tests remain unchanged and pass.
- Added validation for channel/marker uniqueness, aliases, order, colors, coordinate methods, ladder coverage and source provenance.

## 0.3.0 - 2026-07-21

- Added a deterministic, dependency-free, self-contained SVG renderer.
- Added five GlobalFiler channel panels with all 24 marker-range bands.
- Added schematic called-peak glyphs positioned by the v0.2 nominal coordinate model.
- Added allele-ID and RFU labels with deterministic collision-lane allocation.
- Added per-channel, global and fixed RFU scaling with anti-clipping checks.
- Added SVG root, document and peak-level machine-readable metadata.
- Added strict XML 1.0 text validation and restricted stylesheet font input.
- Added explicit handling of unpositioned peaks: fail by default or omit on request.
- Added multi-sample selection checks and the high-level `render_genemapper_epg()` workflow.
- Added validated atomic UTF-8 SVG writing.
- Added a reproducible GlobalFiler example SVG and generation script.
- Added 69 v0.3 tests while retaining 99 non-version-specific v0.2 regression tests.
- Verified predecessor parser, kit, detection, positioning, coordinate data and tests as byte-identical to v0.2.
- Fixed a new workflow bug found during v0.3 testing: the optional `sample_id_column=None` was initially passed through to the parser instead of allowing the parser default.

## 0.2.0 - 2026-07-20

- Added a validated GlobalFiler nominal base-pair coordinate model for all 24 markers and all allelic-ladder alleles.
- Added manufacturer-derived GlobalFiler marker ranges and marker-specific repeat lengths.
- Added explicit Amelogenin and Yindel coordinates and a GlobalFiler-specific TPOX anchor.
- Added immutable positioned-peak/sample models and `position_sample()`.
- Added strict and permissive handling of unknown alleles, unknown markers and dye mismatches.
- Added explicit quality controls preventing approximate coordinates from being claimed as exact GeneMapper bin centres.
- Added packaged JSON data with source notes and validation.
- Corrected coordinate-model caching so kit aliases resolve to the same validated model instance.

## 0.1.0 - 2026-07-20

- Established project scope and standalone architecture.
- Added robust GeneMapper genotype CSV/TSV parser for marker, dye, allele and RFU data.
- Added GlobalFiler kit definition with 24 markers and five sample dye channels.
- Added marker/dye/order-based kit matching and explicit kit override.
- Added comprehensive initial test suite and central test runner.

## 0.8.0

- Added CLI/Python batch rendering for every sample in one GeneMapper export.
- Added deterministic safe filenames and a JSON batch manifest.
- Segmented channel baselines now use equal-width colored and black segments with butt line caps.
- Reduced dynamic space below allele labels without clipping dense profiles.
- Tightened the automatic x-domain to start 5 bp before the shortest marker range.
- Shortened Amelogenin display labels to `AMEL` while preserving canonical marker names.
- Reduced marker-box height while retaining the existing font size.
- Added three RFU axis labels per channel (0, midpoint, exact channel maximum).
- Continued to render every called CSV value, including `OL`, without inferring artefacts.
