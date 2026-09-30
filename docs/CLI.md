# CLI and standalone binaries

The command-line interface renders GeneMapper genotype-table exports without opening
the GUI. An installed package provides `epg-render`; the standalone Windows x64 asset
provides `epg-render.exe` and does not require Python. The
[installation guide](INSTALLATION.md) describes both.

## Verify the command

Installed package:

```bash
epg-render --version
epg-render --help
epg-render --list-kits
```

Standalone Windows executable:

```powershell
.\epg-render.exe --version
.\epg-render.exe --help
.\epg-render.exe --list-kits
```

`--list-kits` reports every bundled profile. A profile is usable for a GeneMapper
workflow only when its definition declares compatible export support.

## Render one sample

```bash
epg-render run.tsv sample.svg --sample-id DNA-123 --kit GlobalFiler
```

`--sample-id` may be omitted when the file contains exactly one sample. `--kit` may be
omitted only when the available marker, dye, and order evidence resolves one compatible
kit unambiguously.

The output suffix selects SVG, PNG, JPG, or JPEG:

```bash
epg-render run.tsv sample.png --sample-id DNA-123 --raster-scale 2
epg-render run.tsv sample.jpg --sample-id DNA-123 --jpeg-quality 95
```

Source and wheel installations require optional raster dependencies and native Cairo.
The verified Windows binaries include the tested raster runtime.

## Render every sample

```bash
epg-render run.tsv rendered --all-samples --format svg --kit GlobalFiler
```

The output directory receives one file per successful sample plus
`epg_batch_manifest.json`. A rerun uses a valid prior manifest as the ownership record
for old renderer-created images. It retires only recorded image files and preserves
unrelated files. A malformed manifest or unsafe recorded filename stops the rerun.

Filenames are derived from the sample identifier: characters outside letters, digits,
`-`, `_` and `.` become underscores, the stem is capped at 120 characters, and names
that would collide receive a numeric suffix. A sample whose name is a reserved Windows
device name (`CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`, `LPT1`–`LPT9`) receives a
trailing underscore on that segment, because Windows cannot create such files even with
a suffix. The manifest always records the filename actually written.

By default, a batch continues after an individual sample error and returns a non-zero
status if any sample failed. Inspect the manifest rather than assuming that every
requested sample was written.

## Frequently used options

| Option | Effect |
|---|---|
| `--sample-id ID` | Select one sample from a multi-sample export |
| `--all-samples` | Render all samples into an output directory |
| `--format svg|png|jpg|jpeg` | Choose batch output format |
| `--kit NAME` | Resolve a specific bundled GeneMapper-compatible kit |
| `--sample-id-column NAME` | Use a non-default source column as sample identifier |
| `--title TEXT` | Override the document title |
| `--yellow-channel yellow|black` | Choose display color for yellow channels |
| `--raster-scale NUMBER` | Set PNG/JPEG scale from 0.1 through 10 |
| `--jpeg-quality NUMBER` | Set JPEG quality from 1 through 100 |
| `--permissive-positioning` | Omit unpositioned peaks instead of failing |

Permissive positioning is not a repair mechanism. It deliberately produces an output
that omits peaks the selected coordinate model cannot place; review recorded issues
before using such an image. It only relaxes allele-level problems. Kit checks run
before positioning and always reject unknown markers and dye conflicts, so such input
ends with exit status `2` in both modes.

## Exit behavior

- Exit status `0` means the requested render completed with every called peak placed
  in the image.
- Exit status `2` covers invalid arguments, rejected input, rendering errors, or a
  batch containing failed samples.
- Exit status `3` means an image was written but at least one called peak could not be
  positioned and is therefore missing from it. This can only occur with
  `--permissive-positioning`; every affected peak is named on standard error.
- The successful single-render path prints the resolved output path.
- The batch path prints the output directory, success/failure counts, and manifest
  path.
- Parser warnings and positioning issues are written to standard error, prefixed with
  `epg-render: warning:`. Parser warnings alone do not change the exit status.
- The batch manifest additionally records `warnings` for the export and `issues` per
  sample.

Automation must check the process exit status and, for batches, the JSON manifest. Do
not infer success merely from the existence of an output directory, and do not treat
exit status `3` as success: the image is incomplete.

## Application integration

An external application should:

1. Keep the standalone executable at a known absolute path.
2. Pass input and output paths as separate process arguments rather than constructing a
   shell command string.
3. Capture the exit status and standard error.
4. Treat status `0` as success and every other status as a failed request.
5. For batch jobs, parse `epg_batch_manifest.json` and handle each item explicitly.

Example PowerShell invocation:

```powershell
& "C:\Tools\EPG-Renderer\epg-render.exe" `
  "C:\Data\run.tsv" `
  "C:\Data\sample.svg" `
  --sample-id "DNA-123" `
  --kit "GlobalFiler"

if ($LASTEXITCODE -ne 0) {
    throw "EPG-Renderer failed with exit code $LASTEXITCODE"
}
```

The standalone CLI does not open the GUI. Executables are operating-system and
architecture specific; a Windows executable cannot run on macOS or Linux.

See the [GeneMapper input requirements](GENEMAPPER.md), [Python vignette](PYTHON.md),
or return to the [documentation home](index.md).
