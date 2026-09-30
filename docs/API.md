# EPG-Renderer API

This document describes the current Python API. The package root intentionally exposes only nine operations and `__version__`.

## Canonical operations

### `load_project(...) -> GeneMapperProject`

Read and validate one configurable GeneMapper genotype-table export. The parser discovers indexed `Allele n`, `Height n`, `Size n`, `Area n`, `Mutation n` and `Comment n` families by suffix. `Dye` is optional, harmless empty trailing export columns are normalized, and duplicate display names remain separate source injections. The returned project, samples, marker mappings and allele calls are immutable defensive copies.

Imported RFU heights must be whole numbers from 0 through 32,767. Larger values raise `NumericConversionError` with the source line and column. Manually entered RFU heights use the stricter range 1 through 32,767 and raise `ManualProfileError`; the manual-profile GUI displays that error without accepting or closing the dialog. `epg_renderer.rfu.MAX_RFU` is the single package-wide upper-bound definition.

```python
from epg_renderer import load_project

project = load_project("run.tsv", export_mode="unknown")
sample = project.sample("DNA-123")
for warning in project.warnings:
    print(warning)
```

### `list_kits(genemapper_only=False) -> tuple[KitProfile, ...]`

Return bundled immutable kit profiles in deterministic resource order. Set `genemapper_only=True` to exclude profiles whose GeneMapper export compatibility has not been verified.

### `load_kit(name) -> KitProfile`

Resolve one profile by canonical name or declared alias. Kit type, export compatibility and marker type are enums; marker metadata and source references are typed immutable values. Source references retain both their title and the fact for which they were used.

### `match_kits(sample, genemapper_only=False) -> tuple[KitMatch, ...]`

Rank kit profiles against observed marker names, available dye evidence and source order. Missing dye information is neutral rather than a mismatch, so a complete marker/order match without exported dyes is classified as high confidence rather than exact. Diagnostic collections in each result are immutable tuples.

### `position_sample(...) -> PositionedSample`

Map exported peaks to kit-specific coordinates. An exported `Size n` value is used directly. Otherwise ladder coordinates are used, with bounded repeat-based estimates available for numeric off-ladder alleles. `PositionedPeak.coordinate_source` distinguishes measured, nominal, estimated, verified exact-bin-centre and unpositioned values; `coordinate_bp` stores the provenance-neutral coordinate. Derived coordinates remain schematic unless explicitly documented as exact.

### `render_svg(sample, ...) -> str`

Render either a parsed `SampleCall` or an already positioned `PositionedSample` as deterministic SVG text. Supplying `kit_name` for an already positioned sample is rejected because the kit is part of that object's immutable state.

### `render_file(...) -> pathlib.Path`

Read one export, select one sample and write SVG, PNG or JPEG. A `sample_id` is required when the export contains more than one sample.

```python
from epg_renderer import render_file

path = render_file(
    "run.tsv",
    "sample.svg",
    sample_id="DNA-123",
    kit_name="GlobalFiler",
)
```

### `render_file_report(...) -> RenderReport`

Same parameters and behavior as `render_file`, but returns a `RenderReport` with the
output path, parser warnings and positioning issues. With permissive positioning an
image can omit called peaks; `has_omitted_peaks` flags that loss and `messages()`
returns every diagnostic as readable text. Applications that present results to users
should prefer this operation.

`strict_positioning=False` only relaxes allele-level problems. The rendering operations
check marker names and dyes against the kit first and always reject unknown markers and
dye conflicts with `KitResolutionError`.

```python
from epg_renderer import render_file_report

report = render_file_report("run.tsv", "sample.svg", sample_id="DNA-123")
for message in report.messages():
    print(message)
```

### `render_batch(...) -> BatchRenderResult`

Render every sample into a target directory. Each `BatchRenderItem` uses the `BatchStatus` enum internally; the JSON manifest serializes the stable string values `"ok"` and `"error"`.

A rerun treats the previous valid manifest as the ownership record for earlier batch
images. It removes exactly those recorded image files before processing the new input,
so failed, removed or renamed samples cannot leave stale results. Other files are not
touched. A malformed manifest or an unsafe recorded filename aborts the rerun.

## Explicit type modules

The package root does not re-export types. Import them from the module that owns their contract:

- `epg_renderer.models`: `AlleleCall`, `MarkerCall`, `SampleCall`, `GeneMapperProject`
- `epg_renderer.domain`: `KitType`, `ExportCompatibility`, `MarkerType`, `BatchStatus`, `ProfileOrigin`, `PeakHeightMode`, `SourceReference`, `MarkerMetadata`
- `epg_renderer.kit_schema`: `KitProfile`, `KitSchemaError`
- `epg_renderer.kit_workflow`: `Confidence`, `KitMatch`, `KitResolutionError`
- `epg_renderer.positions`: coordinate enums, positioned types and positioning errors
- `epg_renderer.render_options`: SVG/raster options, output enums and render errors
- `epg_renderer.batch`: `BatchRenderItem`, `BatchRenderResult`
- `epg_renderer.manual_profile`: validated manual-profile types, parsing helpers and `ManualProfileError`
- `epg_renderer.rfu`: the manufacturer-backed `MAX_RFU` boundary and shared validator
- `epg_renderer.workflow`: `RenderReport` and the lower-level `render_manual_epg` workflow used by the GUI

This separation keeps the root namespace stable and makes dependencies explicit.

## Immutability contract

Public domain and result dataclasses are frozen and use slots. `SampleCall.origin` and `SampleCall.height_mode` explicitly distinguish GeneMapper/RFU data from manually entered RFU or uniform non-quantitative profiles. `SampleCall.sample_id` is the unique project identifier; `display_name`, `sample_name`, `sample_file`, `source_sample_id` and `run_name` retain source identity separately. Incoming lists and mappings are copied into tuples or read-only mapping views during construction, so later mutation of a caller-owned builder cannot alter a validated object. Constructors reject contradictory keys, invalid enum types and malformed core values before an object is exposed.

Positioned values additionally enforce finite, ordered coordinate ranges, coordinate/source consistency, positive allele indexes and RFU/height-mode consistency. Manual-profile values enforce allele/RFU cardinality and height-mode consistency. Batch items enforce that successful outcomes have an output and no error, while failed outcomes have an error and no output. These constructors do not load kit definitions or inspect files: kit-dependent and filesystem-dependent validation remains at the relevant operation boundary.

## Error boundaries

The high-level operations use dedicated parser, kit-resolution, coordinate, sample-selection, SVG and raster exceptions. Applications should catch the narrow error class from the relevant subject module rather than catching `Exception`.
