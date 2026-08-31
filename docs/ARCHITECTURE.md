# Architecture

EPG-Renderer separates public orchestration, immutable domain state, data ingestion, kit knowledge, coordinate placement and presentation.

- `api.py` defines the eight canonical package operations.
- `domain.py` contains typed enums and immutable kit/batch metadata.
- `models.py` contains immutable project, sample, marker and allele structures shared by parsed and manual inputs.
- `parser.py` separates source decoding, CSV syntax validation, table-shape normalization, semantic header-family interpretation, source-injection identity and row accumulation before publishing immutable models.
- `kit_schema.py` validates declarative kit profiles and constructs typed immutable metadata.
- `kit_registry.py` loads and caches bundled profiles.
- `kit_workflow.py` detects kits, resolves one profile and coordinates positioning.
- `positions.py` defines nominal kit coordinate models and provenance-aware positioned peaks.
- `render_options.py` validates rendering configuration through small field-specific validators.
- `render_layout.py` contains deterministic layout calculations.
- `render_document.py` validates positioned samples, prepares document plans and assembles SVG metadata, headings, channels and footers.
- `render_svg.py` contains channel-level SVG drawing and geometry primitives without document orchestration.
- `render_io.py` performs atomic SVG and optional raster writes.
- `manual_profile.py` validates kit-aware manual inputs and converts them into the shared sample model without synthetic CSV files or invented RFU values.
- `manual_gui.py` provides the modal, scrollable manual-profile editor while keeping validation outside Tkinter code.
- `workflow.py` orchestrates one-sample GeneMapper and manual-profile rendering.
- `batch.py` validates an immutable batch request and confines mutable per-run state to one runner responsible for sample isolation, manifest creation and manifest-scoped retirement of prior batch outputs.
- `cli.py` and `gui.py` are user-interface adapters.

The package root imports only the canonical operations and `__version__`. Types and lower-level helpers remain in their subject modules; cache controls, validators and internal render functions are not accidental root-level API.

The JSON kit registry is the only source of bundled marker, channel, alias and coordinate information. Rendering code must not embed kit-specific marker lists or coordinate tables.

The parser treats GeneMapper as a configurable table export: scalar metadata and indexed peak families are interpreted independently, missing evidence is preserved as missing, and warnings report non-fatal uncertainty such as possible allele-width truncation. Mutable state is confined to parsing and accumulation boundaries. Public projects, calls, kit metadata, match results, positioned samples and batch results defensively copy nested collections and expose immutable tuples or mapping views. Their constructors enforce locally decidable scalar, collection and cross-field invariants. A coordinate model owns its immutable kit definition, so marker resolution and model validation do not depend on the global kit registry; checks requiring filesystem or bundled-resource knowledge remain in the workflows that own that context.

Dependencies point inward: interface modules call workflows; file and manual workflows converge on the same immutable sample, positioning and rendering pipeline; core modules do not import CLI or GUI code.

## Development and release tooling

Check and release modules live under `tools/` and have deliberately separate responsibilities. `tools.run_all_tests` is the normal development entry point. `tools.run_release_checks` is the release-level orchestrator; it delegates static analysis and compilation to `tools.run_quality_checks`, delegates coverage-enforced tests to `tools.run_coverage_checks`, and then invokes deterministic artifact verification from `tools.release_tools`. `tests/smoke/source_smoke_test.py` is a narrow extracted-source artifact check used within that release workflow.

Deterministic unit tests verify the renderer's internal layout calculations. A separate raster-enabled geometry test uses CairoSVG and Pillow to measure actual rendered glyph pixels without calling the production width estimator. It checks fit and overlap properties rather than platform-specific pixel snapshots, while the CI matrix exercises the available font fallbacks on Linux, Windows and macOS. These test dependencies do not become core runtime dependencies.

The canonical tool set is unversioned and unique. Copy-generated siblings such as `tools/run_quality_checks_2.py` or `tools/run_release_checks_2.py` are not supported source files. The explicit release allowlist rejects them, and source-tree regression tests guard against their accidental introduction.
