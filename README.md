# EPG-Renderer

EPG-Renderer creates schematic, kit-aware electropherogram-style figures from forensic
STR data. It reads GeneMapper genotype-table CSV/TSV exports or builds a profile from
alleles entered manually in the graphical interface.

The program is a visualization tool. It does not read raw capillary-electrophoresis
data, reconstruct measured fluorescence curves, or replace analytical interpretation
and quality control.

## Example output

[![Synthetic two-person PowerPlex ESI 17 Fast electropherogram](https://raw.githubusercontent.com/rsivth/EPG-Renderer/main/examples/esi17_two_person_mixture_example.svg)](https://github.com/rsivth/EPG-Renderer/blob/main/examples/esi17_two_person_mixture_example.svg)

## Choose a download

Use PyPI for Python installations and the
[EPG-Renderer Releases page](https://github.com/rsivth/EPG-Renderer/releases) for
standalone Windows binaries and the complete source ZIP.

| Goal | Distribution | Python required? |
|---|---|---:|
| Run the graphical interface on Windows x64 | `EPG-Renderer_GUI_Windows_x64_vX.Y.Z.zip` | No |
| Integrate the Windows command-line renderer | `epg-render.exe` | No |
| Use SVG rendering from the CLI or Python | `python3 -m pip install epg-renderer` | Yes, Python 3.10+ |
| Add PNG and JPEG output | `python3 -m pip install "epg-renderer[raster]"` | Yes, plus native Cairo |
| Run the GUI directly from source | `EPG-Renderer_vX.Y.Z.zip` | Yes, Python 3.10+ with Tkinter |

The initial binary release target is Windows x64. The PyPI package is operating-system
independent; Tkinter and native Cairo remain system components where the GUI or raster
output needs them. Verify GitHub release assets against their published SHA-256
checksums before use.

## Quick start

### Python package from PyPI

Install the dependency-free SVG core:

```bash
python3 -m pip install epg-renderer
epg-render --version
```

For PNG and JPEG output, install `epg-renderer[raster]` and provide native Cairo. Start
the installed GUI with `epg-render-gui` when the Python installation includes Tkinter.

### Windows GUI without Python

1. Download the versioned Windows GUI ZIP from the Releases page.
2. Extract the complete ZIP; do not run the application from inside the archive.
3. Open the extracted `EPG-Renderer-GUI` folder and start
   `EPG-Renderer-GUI.exe`.
4. Keep SVG selected unless a raster image is specifically required.

The initial executable may be unsigned, so Windows can show a SmartScreen warning.
Verify the checksum and release source before deciding whether your local security
policy permits the application.

### GUI from an extracted source ZIP

Windows:

```bat
py -3 launch_gui.py
```

macOS or Linux:

```bash
python3 launch_gui.py
```

The source launcher needs Tkinter but does not require the package to be installed.
See the
[Getting started and GUI manual](https://github.com/rsivth/EPG-Renderer/blob/main/docs/GETTING_STARTED.md)
for installation, manual-profile entry, and troubleshooting.

### Command line

An installed package provides `epg-render`; a standalone Windows download provides
`epg-render.exe`.

```bash
epg-render run.tsv sample.svg --sample-id DNA-123 --kit GlobalFiler
epg-render run.tsv output_directory --all-samples --format svg --kit GlobalFiler
```

See the
[CLI and standalone binary guide](https://github.com/rsivth/EPG-Renderer/blob/main/docs/CLI.md)
for all normal workflows, exit behavior, and application integration.

### Python

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

See the [Python vignette](https://github.com/rsivth/EPG-Renderer/blob/main/docs/PYTHON.md)
and [API reference](https://github.com/rsivth/EPG-Renderer/blob/main/docs/API.md).

## Capabilities

- SVG, PNG, and JPEG output from GeneMapper genotype-table exports
- GUI-based GeneMapper import and kit-aware manual profile entry
- explicit RFU or uniform non-quantitative manual peak-height modes
- batch rendering with one image per sample and a JSON manifest
- automatic or explicit kit resolution using 14 bundled profiles
- deterministic SVG output and reproducible source, wheel, and Windows builds
- fully local processing without profile-data uploads

SVG is the recommended output format because it is scalable, editable, and requires
no raster libraries. Source and wheel installations need Pillow, CairoSVG, and a
working native Cairo library for PNG/JPEG output. Verified Windows binaries include
their required raster runtime.

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
