---
title: EPG-Renderer documentation
---

# EPG-Renderer documentation

EPG-Renderer creates schematic, kit-aware electropherogram-style figures from
GeneMapper genotype-table exports or manually entered STR profiles. Start with the
guide that matches your task.

| Task | Guide |
|---|---|
| Download and start the graphical interface | [Getting started and GUI manual](GETTING_STARTED.md) |
| Render from a terminal or another application | [CLI and standalone binaries](CLI.md) |
| Use EPG-Renderer from Python | [Python vignette](PYTHON.md) |
| Check public functions and type ownership | [API reference](API.md) |
| Prepare or diagnose a GeneMapper export | [GeneMapper input requirements](GENEMAPPER.md) |
| Understand peak coordinates and scientific limits | [Coordinate model](COORDINATE_MODEL.md) and [sources](SOURCES.md) |
| Develop, test, or release the project | [Development guide](DEVELOPMENT.md) |
| Add or review a kit definition | [Declarative kit format](KIT_FORMAT.md) |
| Understand internal boundaries | [Architecture](ARCHITECTURE.md) |

## Downloads

Install the Python package with `python -m pip install epg-renderer`. The
[EPG-Renderer Releases page](https://github.com/rsivth/EPG-Renderer/releases) provides
the complete source ZIP and platform-specific assets. Verify GitHub downloads against
the published SHA-256 checksums. The initial standalone binary target is Windows x64;
the PyPI wheel and standard source distribution support the documented Python
versions across operating systems.

## Scientific scope

EPG-Renderer visualizes called STR peaks. It does not read raw electrophoresis files,
reconstruct fluorescence traces, perform allele calling, or replace forensic
interpretation and quality control. Coordinates are measured only when the source
export supplies fragment sizes; otherwise their provenance remains explicitly
nominal, estimated, or verified exact-bin-centre.

All rendering is local. The application does not upload profile data.

Return to the [project overview](../README.md) or review the
[release history](../CHANGELOG.md).
