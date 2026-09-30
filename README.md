# EPG-Renderer

EPG-Renderer turns forensic STR profiles into clear, kit-aware electropherogram-style
figures. Load a GeneMapper genotype-table export or type in the alleles, and every peak
appears in its dye channel at its place in the kit's size range, with marker and allele
labels.

- **Publications and expert reports:** SVG is vector graphics and stays sharp at any
  size; refine the figure in Inkscape or Adobe Illustrator.
- **Teaching and training:** enter invented profiles by hand to show heterozygous
  loci, shared alleles or mixtures, without using casework data.
- **Slides and lectures:** create PNG or JPG for PowerPoint or Keynote.

## Example output

[![Synthetic two-person PowerPlex ESI 17 Fast electropherogram](https://raw.githubusercontent.com/rsivth/EPG-Renderer/main/examples/esi17_two_person_mixture_example.svg)](https://github.com/rsivth/EPG-Renderer/blob/main/examples/esi17_two_person_mixture_example.svg)

## Capabilities

- SVG, PNG, and JPEG output from GeneMapper genotype-table exports
- GUI-based GeneMapper import and kit-aware manual profile entry
- explicit RFU or uniform non-quantitative manual peak-height modes
- batch rendering with one image per sample and a JSON manifest
- automatic or explicit kit resolution using 14 bundled profiles
- deterministic SVG output and byte-reproducible source ZIP, source distribution, and
  wheel builds
- fully local processing without profile-data uploads

## Documentation

Start at the [documentation home](https://github.com/rsivth/EPG-Renderer/blob/main/docs/index.md) or go directly to your task.

**Create a figure without programming**

- Windows: [download and start the GUI](https://github.com/rsivth/EPG-Renderer/blob/main/docs/INSTALLATION.md#windows-gui); Python
  is not needed.
- macOS and Linux: [start the GUI with Python](https://github.com/rsivth/EPG-Renderer/blob/main/docs/INSTALLATION.md#gui-with-python).
- [GUI guide](https://github.com/rsivth/EPG-Renderer/blob/main/docs/GETTING_STARTED.md): from export or manual entry to the finished
  figure, and which format to choose.

**Use EPG-Renderer in your software**

- [Install the Python package](https://github.com/rsivth/EPG-Renderer/blob/main/docs/INSTALLATION.md#python-package): the wheel from
  the [Releases page](https://github.com/rsivth/EPG-Renderer/releases); EPG-Renderer is
  not on PyPI.
- [Command line and standalone Windows `epg-render.exe`](https://github.com/rsivth/EPG-Renderer/blob/main/docs/CLI.md)
- [Python vignette](https://github.com/rsivth/EPG-Renderer/blob/main/docs/PYTHON.md) and [API reference](https://github.com/rsivth/EPG-Renderer/blob/main/docs/API.md)

**Background and development**

- [GeneMapper input requirements](https://github.com/rsivth/EPG-Renderer/blob/main/docs/GENEMAPPER.md),
  [coordinate model](https://github.com/rsivth/EPG-Renderer/blob/main/docs/COORDINATE_MODEL.md) and
  [sources and provenance](https://github.com/rsivth/EPG-Renderer/blob/main/docs/SOURCES.md)
- [Development and release checks](https://github.com/rsivth/EPG-Renderer/blob/main/docs/DEVELOPMENT.md),
  [architecture](https://github.com/rsivth/EPG-Renderer/blob/main/docs/ARCHITECTURE.md) and
  [declarative kit format](https://github.com/rsivth/EPG-Renderer/blob/main/docs/KIT_FORMAT.md)
- Release history: [changelog](https://github.com/rsivth/EPG-Renderer/blob/main/CHANGELOG.md)

## Scope and limitations

- EPG-Renderer is a visualization tool. It does not reconstruct measured
  fluorescence curves or replace analytical interpretation and quality control.
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

## License

EPG-Renderer is distributed under the BSD 3-Clause License. See the
[license text](https://github.com/rsivth/EPG-Renderer/blob/main/LICENSE).
