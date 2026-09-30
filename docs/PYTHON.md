# Python vignette

The Python package exposes nine stable root-level operations and `__version__`.
Lower-level types and exceptions remain in the modules that own their contracts.

## Installation

Install the package from PyPI:

```bash
python -m pip install epg-renderer
```

Or install an extracted source tree for development:

```bash
python -m pip install .
```

For PNG and JPEG output, install the raster extra and provide native Cairo:

```bash
python -m pip install "epg-renderer[raster]"
```

Use `python -m pip install ".[raster]"` instead when installing the checked-out source
tree. SVG rendering has no third-party runtime dependency.

## Render one file

```python
from epg_renderer import render_file

output = render_file(
    "run.tsv",
    "sample.svg",
    sample_id="DNA-123",
    kit_name="GlobalFiler",
)
print(output)
```

When the export contains exactly one sample, `sample_id` can be omitted. When kit
evidence resolves one compatible profile unambiguously, `kit_name` can also be
omitted.

`render_file` returns only the output path. Use `render_file_report` with the same
arguments when parser warnings and positioning issues must be shown:

```python
from epg_renderer import render_file_report

report = render_file_report("run.tsv", "sample.svg", sample_id="DNA-123")
if report.has_omitted_peaks:
    print("The image is missing at least one called peak.")
for message in report.messages():
    print(message)
```

## Inspect samples and parser warnings

```python
from epg_renderer import load_project

project = load_project("run.tsv")

for sample_id, sample in project.samples.items():
    print(sample_id, sample.display_name)

for warning in project.warnings:
    print("Warning:", warning)
```

`sample_id` is the unique project identifier. Display name, source sample ID, sample
file, and run name remain separately available when exported. Duplicate display names
are not silently merged.

## List and inspect bundled kits

```python
from epg_renderer import list_kits, load_kit

for profile in list_kits(genemapper_only=True):
    print(profile.kit.name, profile.manufacturer)

globalfiler = load_kit("GlobalFiler")
print(globalfiler.kit.display_name)
```

Use `match_kits(sample, genemapper_only=True)` when an application needs ranked match
evidence rather than automatic resolution.

## Customize rendering

```python
from epg_renderer import render_file
from epg_renderer.render_options import RasterRenderOptions, SvgRenderOptions

svg_options = SvgRenderOptions(
    title="DNA-123",
    yellow_channel_mode="black",
    rfu_scale_mode="global",
)
raster_options = RasterRenderOptions(scale=2.0, jpeg_quality=95)

render_file(
    "run.tsv",
    "sample.jpg",
    sample_id="DNA-123",
    kit_name="GlobalFiler",
    options=svg_options,
    raster_options=raster_options,
)
```

Option objects are validated at the rendering boundary. Invalid dimensions, modes,
RFU scales, raster factors, and unsafe text fail explicitly.

## Render every sample

```python
from epg_renderer import render_batch
from epg_renderer.render_options import OutputFormat

result = render_batch(
    "run.tsv",
    "rendered_samples",
    output_format=OutputFormat.SVG,
    kit_name="GlobalFiler",
)

print(f"Rendered: {result.succeeded}; failed: {result.failed}")
print(f"Manifest: {result.manifest_path}")

for item in result.items:
    print(item.sample_id, item.status, item.output_path, item.error)
```

Batch output lifecycle is manifest-scoped: prior renderer-owned images can be retired,
while unrelated files are preserved. A malformed or unsafe prior manifest aborts the
operation.

## Work with parsed samples

```python
from epg_renderer import load_project, position_sample, render_svg

project = load_project("run.tsv")
sample = project.sample("DNA-123")
positioned = position_sample(sample, kit_name="GlobalFiler", genemapper_only=True)
svg_text = render_svg(positioned)
```

Parsed projects, samples, marker calls, kit profiles, match results, positioned peaks,
and batch results are immutable. Construct a new validated request rather than
mutating returned state.

## Error handling

Catch the narrow exception owned by the relevant boundary instead of catching every
exception. Important modules include:

- `epg_renderer.parser` for decoding, schema, and numeric input errors
- `epg_renderer.kit_workflow` for kit resolution and matching errors
- `epg_renderer.positions` for coordinate and allele-positioning errors
- `epg_renderer.render_options` for selection, SVG, and raster errors
- `epg_renderer.manual_profile` for validated manual-profile input

The [API reference](API.md) lists the canonical operations and type ownership. Also
see the [GeneMapper input requirements](GENEMAPPER.md) and
[coordinate model](COORDINATE_MODEL.md).

## Compatibility policy

The names listed in `epg_renderer.__all__`, their documented keyword arguments, and
the two console commands are the supported public surface. Internal modules and
unexported names may change without compatibility guarantees. Before version 1.0,
necessary public changes are announced in the changelog and should not be assumed to
be backward-compatible merely because the release remains in the `0.x` series.
