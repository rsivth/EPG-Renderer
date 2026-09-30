# Getting started and GUI manual

This guide covers the graphical interface for users who want to create an EPG without
writing Python code. SVG is the recommended output format.

## Choose the appropriate distribution

| Environment | Recommended file | Additional requirement |
|---|---|---|
| Windows x64 without Python | Versioned Windows GUI ZIP | None |
| Windows, macOS, or Linux with Python | Source ZIP | Python 3.10+ with Tkinter |
| Existing Python environment | PyPI package | Python 3.10+; Tkinter for the GUI |

Use PyPI for a normal Python installation and the
[EPG-Renderer Releases page](https://github.com/rsivth/EPG-Renderer/releases) for
standalone Windows binaries or the complete source ZIP. Do not mix files from
different versions.

## Windows GUI without Python

1. Download `EPG-Renderer_GUI_Windows_x64_vX.Y.Z.zip` and the published checksums.
2. Verify the ZIP in PowerShell, replacing the example filename with the downloaded
   version:

   ```powershell
   Get-FileHash .\EPG-Renderer_GUI_Windows_x64_vX.Y.Z.zip -Algorithm SHA256
   ```

3. Compare the complete digest with the release checksum.
4. Extract the entire ZIP to a normal folder. Running from inside the ZIP is not
   supported.
5. Open the extracted `EPG-Renderer-GUI` folder and start
   `EPG-Renderer-GUI.exe`.

The initial executable may not be code-signed. Windows can therefore show a
SmartScreen warning even when the checksum matches. Follow local security policy; a
checksum confirms file identity but is not a substitute for organizational approval.

The Windows GUI bundle contains its Python, Tkinter, raster, and kit-resource runtime.
It does not require a separate Python installation.

## GUI from source

Extract the complete source ZIP before running any command. The package itself does
not need to be installed for this workflow.

### Windows

Install Python 3.10 or newer with the optional Tcl/Tk component, then run in the
extracted project folder:

```bat
py -3 launch_gui.py
```

Diagnostic checks:

```bat
py -3 -m tkinter
py -3 launch_gui.py --check
```

The first command should open a small Tk window. The second should report that the
offline GUI launcher is ready.

### macOS

Use a Python installation that includes Tkinter:

```bash
python3 -m tkinter
python3 launch_gui.py
```

### Linux

Install Python 3.10 or newer plus the distribution's Tkinter package, commonly named
`python3-tk`, then run:

```bash
python3 launch_gui.py
```

## GUI from an installed package

Install from PyPI and start the generated GUI command:

```bash
python -m pip install epg-renderer
epg-render-gui
```

If the generated command is not on the executable path, use:

```bash
python -m epg_renderer.gui
```

## Create an image from a GeneMapper export

1. Select **Choose GeneMapper file…** and open the CSV, TSV, or TXT genotype-table
   export.
2. If the file contains multiple sample injections, select the required sample.
3. Confirm the automatically resolved kit. If several profiles are compatible,
   select the correct kit explicitly.
4. Choose SVG, PNG, or JPG and review the proposed output path.
5. Under **Yellow dye shown as**, keep **Yellow** or choose **Black (better contrast)**
   when yellow peaks are hard to read, for example on a projector.
6. Select **Create image**.

The GUI does not guess when no compatible kit can be established. See the
[GeneMapper input requirements](GENEMAPPER.md) when a file is rejected or kit
selection remains unavailable.

## Create a manual profile

1. Select **Create manually…**.
2. Choose the kit and enter a meaningful profile name.
3. Enter one or more alleles for each required marker. Separate multiple values with
   commas, semicolons, or spaces. Empty markers are permitted.
4. Choose one peak-height mode:

   - **Uniform schematic heights** records no RFU measurements, omits the RFU axis,
     and marks the output as non-quantitative.
   - **Enter RFU heights** requires one whole-number height from 1 through 32,767 for
     every entered allele.

5. Select **Use profile**, review the output settings, and create the image.

Technical kit controls are excluded from manual entry. Numerical off-ladder alleles
are accepted only when the selected coordinate model can position them safely.

## Output formats

- **SVG** is scalable, editable, and available without raster dependencies.
- **PNG** and **JPG** are convenient for applications that cannot display SVG.
- Windows binaries contain the tested raster runtime.
- PyPI installations require the `raster` extra and native Cairo:

  ```bash
  python -m pip install "epg-renderer[raster]"
  ```

  For an extracted source tree, use its local extra instead:

  ```bash
  python -m pip install ".[raster]"
  ```

If native Cairo is unavailable, use SVG and convert the result with a trusted graphics
application.

## Troubleshooting

### The application does not start

- Confirm that the complete archive was extracted.
- For the source launcher, verify Tkinter with `python -m tkinter`.
- A source-launcher failure can create `EPG-Renderer_startup_error.log` beside
  `launch_gui.py`; it can contain local paths, so review it before sharing.
- For a Windows binary, verify the checksum and confirm that antivirus or application
  policy did not quarantine part of the extracted bundle.

### The GeneMapper file is rejected

Do not remove columns at random. Compare the export with the explicit
[input contract](GENEMAPPER.md); parser errors identify the violated boundary.

### PNG or JPG fails

Use SVG first. A source or wheel installation needs both the Python raster packages
and a working native Cairo library.

## Privacy and interpretation

EPG-Renderer performs its work locally and does not upload profile data. The output is
a schematic representation of called peaks, not a reconstruction of raw fluorescence
signal and not an independent analytical interpretation.

Continue with the [CLI guide](CLI.md), [Python vignette](PYTHON.md), or return to the
[documentation home](index.md).
