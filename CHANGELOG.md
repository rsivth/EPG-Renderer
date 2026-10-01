# Changelog

## Unreleased

This is the first public release of EPG-Renderer. It creates schematic, kit-aware
electropherogram-style figures from forensic STR profiles for publications, teaching
and slides.

### Downloads

- **Windows GUI:** `EPG-Renderer_GUI_Windows_x64_v0.14.0.zip`; extract it and start
  `EPG-Renderer-GUI.exe`. Python is not needed; PNG and JPG output are included.
- **Windows command line:** `epg-render.exe`, a standalone program.
- **Source ZIP:** `EPG-Renderer_v0.14.0.zip`, to start the GUI with Python on macOS,
  Linux or Windows.
- **Python wheel:** for the command line and the Python API. EPG-Renderer is not on
  PyPI; install the wheel from this release as described in the installation guide.
- **`SHA256SUMS.txt`:** SHA-256 checksums of all files above.

### What EPG-Renderer does

- reads GeneMapper genotype-table exports (CSV, TSV or TXT) or builds a profile from
  alleles entered manually in the graphical interface
- resolves the kit automatically or uses the selected one; 14 kit profiles are
  included
- draws every peak in its dye channel with marker and allele labels; uses exported
  fragment sizes when present and otherwise labelled nominal or estimated positions
- writes SVG for editing in a vector graphics program, and PNG or JPG for slides; the
  GUI preselects PNG when PNG and JPG output are available
- shows the yellow dye in yellow or, for better contrast, in black
- renders one sample or all samples of an export, with a JSON manifest for batches
- offers the same functions on the command line and through a Python API that reports
  parser warnings and omitted peaks
- processes everything locally; no profile data is uploaded

### Scope

EPG-Renderer is a visualization tool. It does not read raw capillary-electrophoresis
data, reconstruct measured fluorescence curves, or replace analytical interpretation
and quality control. Nominal and estimated positions are not measured fragment sizes.

## Earlier development versions

Versions 0.1.0 to 0.13.49 and the development versions before this release were not
published.
