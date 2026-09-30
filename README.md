# EPG-Renderer

EPG-Renderer creates schematic, kit-aware electropherogram-style figures from forensic
STR data. It reads GeneMapper genotype-table CSV/TSV exports or builds a profile from
alleles entered manually in the graphical interface.

The program is a visualization tool. It does not read raw capillary-electrophoresis
data, reconstruct measured fluorescence curves, or replace analytical interpretation
and quality control.

## Example output

[![Synthetic two-person PowerPlex ESI 17 Fast electropherogram](https://raw.githubusercontent.com/rsivth/EPG-Renderer/main/examples/esi17_two_person_mixture_example.svg)](https://github.com/rsivth/EPG-Renderer/blob/main/examples/esi17_two_person_mixture_example.svg)

## Create a figure without programming

The graphical interface reads a GeneMapper export or lets you enter alleles manually,
resolves the kit and creates the image.

- **Windows:** download the GUI ZIP from the
  [Releases page](https://github.com/rsivth/EPG-Renderer/releases), extract it and
  start `EPG-Renderer-GUI.exe`. Python is not needed.
- **macOS and Linux:** the GUI runs with Python 3.10 or newer including Tkinter.

Step by step:
[installation guide](https://github.com/rsivth/EPG-Renderer/blob/main/docs/INSTALLATION.md)
and [GUI guide](https://github.com/rsivth/EPG-Renderer/blob/main/docs/GETTING_STARTED.md).

For slides, for example in PowerPoint or Keynote, create PNG or JPG. Create SVG to edit
the figure in a vector graphics program such as Inkscape or Adobe Illustrator.

## Use EPG-Renderer in your software

```bash
python3 -m pip install epg-renderer
```

This installs SVG output, the `epg-render` command and the Python API. PNG and JPG
output, source installs and the standalone Windows `epg-render.exe` are covered in the
[installation guide](https://github.com/rsivth/EPG-Renderer/blob/main/docs/INSTALLATION.md).

### Command line

```bash
epg-render run.tsv sample.svg --sample-id DNA-123 --kit GlobalFiler
epg-render run.tsv output_directory --all-samples --format svg --kit GlobalFiler
```

See the [CLI guide](https://github.com/rsivth/EPG-Renderer/blob/main/docs/CLI.md)
for all workflows, exit behavior, and application integration.

### Python

```python
from epg_renderer import render_file_report

report = render_file_report(
    "run.tsv",
    "sample.svg",
    sample_id="DNA-123",
    kit_name="GlobalFiler",
)
print(report.output_path)
for message in report.messages():
    print(message)
```

Show these messages to your users: parser warnings, for example about an export that
may have cut off alleles, do not stop rendering.

See the [Python vignette](https://github.com/rsivth/EPG-Renderer/blob/main/docs/PYTHON.md)
and [API reference](https://github.com/rsivth/EPG-Renderer/blob/main/docs/API.md).

## Capabilities

- SVG, PNG, and JPEG output from GeneMapper genotype-table exports
- GUI-based GeneMapper import and kit-aware manual profile entry
- explicit RFU or uniform non-quantitative manual peak-height modes
- batch rendering with one image per sample and a JSON manifest
- automatic or explicit kit resolution using 14 bundled profiles
- deterministic SVG output and byte-reproducible source ZIP, source distribution, and
  wheel builds
- fully local processing without profile-data uploads

## Scope and limitations

- Input must be a GeneMapper genotype-table export, not an `.fsa` file or other raw
  capillary-electrophoresis data.
- Exported `Size n` values are used when present. Otherwise, peak positions are
  nominal display coordinates or bounded estimates unless a kit explicitly declares
  verified exact bin centres.
- Nominal and estimated coordinates are not measured sample fragment sizes or
  official GeneMapper bins.
- Imported RFU values are structural inputs subject to a 32,767-RFU package ceiling;
  instrument-specific off-scale review remains an upstream responsibility.
- Manually entered profiles are visibly and machine-readably identified as schematic
  manual profiles.

Read the
[GeneMapper input requirements](https://github.com/rsivth/EPG-Renderer/blob/main/docs/GENEMAPPER.md),
[coordinate model](https://github.com/rsivth/EPG-Renderer/blob/main/docs/COORDINATE_MODEL.md),
and [sources and provenance](https://github.com/rsivth/EPG-Renderer/blob/main/docs/SOURCES.md)
before scientific use.

## Documentation

The [documentation home](https://github.com/rsivth/EPG-Renderer/blob/main/docs/index.md)
routes users to:

- [Installation](https://github.com/rsivth/EPG-Renderer/blob/main/docs/INSTALLATION.md)
- [Getting started and GUI manual](https://github.com/rsivth/EPG-Renderer/blob/main/docs/GETTING_STARTED.md)
- [CLI and standalone binaries](https://github.com/rsivth/EPG-Renderer/blob/main/docs/CLI.md)
- [Python vignette](https://github.com/rsivth/EPG-Renderer/blob/main/docs/PYTHON.md)
- [API reference](https://github.com/rsivth/EPG-Renderer/blob/main/docs/API.md)
- [GeneMapper input requirements](https://github.com/rsivth/EPG-Renderer/blob/main/docs/GENEMAPPER.md)
- [Development and release checks](https://github.com/rsivth/EPG-Renderer/blob/main/docs/DEVELOPMENT.md)
- [Architecture](https://github.com/rsivth/EPG-Renderer/blob/main/docs/ARCHITECTURE.md)
  and [declarative kit format](https://github.com/rsivth/EPG-Renderer/blob/main/docs/KIT_FORMAT.md)

Release history is recorded in the
[changelog](https://github.com/rsivth/EPG-Renderer/blob/main/CHANGELOG.md).

## License

EPG-Renderer is distributed under the BSD 3-Clause License. See the
[license text](https://github.com/rsivth/EPG-Renderer/blob/main/LICENSE).
