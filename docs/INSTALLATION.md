# Installation

Choose the section that matches how you want to use EPG-Renderer. Downloads are on the
[EPG-Renderer Releases page](https://github.com/rsivth/EPG-Renderer/releases),
including the Python package. Do not mix files from different versions.

| You want to | Section | Python needed? |
|---|---|---|
| Use the graphical interface on Windows | [Windows GUI](#windows-gui) | No |
| Use the graphical interface on macOS or Linux | [GUI with Python](#gui-with-python) | Yes, 3.10+ with Tkinter |
| Render from a terminal or another program on Windows | [Windows command-line program](#windows-command-line-program) | No |
| Use the command line or the Python API | [Python package](#python-package) | Yes, 3.10+ |

## Windows GUI

1. On the Releases page, download `EPG-Renderer_GUI_Windows_x64_vX.Y.Z.zip`.
2. Extract the complete ZIP to a normal folder, for example with right-click →
   **Extract All…**. Do not start the program from inside the ZIP.
3. Open the extracted `EPG-Renderer-GUI` folder and double-click
   `EPG-Renderer-GUI.exe`.

The program is not code-signed. On the first start, Microsoft Defender SmartScreen can
show **Windows protected your PC**. Select **More info** and then **Run anyway** if
your organization allows running downloaded programs. If there is no **Run anyway**
button, a policy probably blocks the program; ask your IT department.

The ZIP contains everything the program needs, including PNG and JPG support. No
Python installation is required.

### Optional: verify the download

IT departments can compare the ZIP with the SHA-256 checksum published with the
release. In PowerShell, in the download folder:

```powershell
Get-FileHash .\EPG-Renderer_GUI_Windows_x64_vX.Y.Z.zip -Algorithm SHA256
```

A matching checksum confirms the file's identity; it does not replace your
organization's approval process.

## GUI with Python

This works on macOS, Linux and Windows.

1. Install Python 3.10 or newer that includes Tkinter:
   - macOS and Windows: Python from python.org. If the Windows installer offers the
     optional **tcl/tk and IDLE** component, keep it selected.
   - Linux: the distribution's Python plus its Tkinter package, commonly named
     `python3-tk`.
2. Download the source ZIP `EPG-Renderer_vX.Y.Z.zip` from the Releases page and
   extract it completely.
3. Open a terminal in the extracted folder and start the GUI.

   macOS or Linux:

   ```bash
   python3 launch_gui.py
   ```

   Windows:

   ```bat
   py -3 launch_gui.py
   ```

The package does not need to be installed for this. SVG output always works; PNG and
JPG output additionally need the [raster components](#png-and-jpg-output).

## Windows command-line program

Download `epg-render.exe` from the Releases page. It needs neither an installation nor
Python. Check it in a terminal:

```powershell
.\epg-render.exe --version
```

The [CLI guide](CLI.md) describes all commands.

## Python package

EPG-Renderer is not on PyPI. Install the wheel from the Releases page by its address;
replace both `X.Y.Z` with the version shown on the Releases page:

```bash
python -m pip install "epg-renderer @ https://github.com/rsivth/EPG-Renderer/releases/download/vX.Y.Z/epg_renderer-X.Y.Z-py3-none-any.whl"
```

This provides SVG output, the `epg-render` command and the Python API without
third-party runtime dependencies. On macOS and Linux, use `python3` if `python` is not
available.

To install an extracted source ZIP instead, run in its folder:

```bash
python -m pip install .
```

### PNG and JPG output

PNG and JPG need the raster extra and a working native Cairo library:

```bash
python -m pip install "epg-renderer[raster] @ https://github.com/rsivth/EPG-Renderer/releases/download/vX.Y.Z/epg_renderer-X.Y.Z-py3-none-any.whl"
```

For an extracted source ZIP, use `python -m pip install ".[raster]"` instead.

Native Cairo is a system library. On macOS with Homebrew, install it with
`brew install cairo`; if CairoSVG still cannot find it, set
`DYLD_FALLBACK_LIBRARY_PATH` to the output of `brew --prefix cairo` followed by
`/lib`. On Linux, install the distribution's Cairo package. If native Cairo is
unavailable, create SVG and export it with a vector graphics program.

### GUI from the installed package

With a Python that includes Tkinter, the installed package provides the GUI command:

```bash
epg-render-gui
```

If that command is not on the executable path, use `python -m epg_renderer.gui`.

## If the program does not start

- Make sure the complete ZIP was extracted.
- Windows GUI: check whether antivirus software or an application policy quarantined
  part of the extracted folder.
- GUI with Python: `python3 -m tkinter` (Windows: `py -3 -m tkinter`) must open a
  small window. `python3 launch_gui.py --check` must report that the offline GUI
  launcher is ready.
- A failed start of `launch_gui.py` can write `EPG-Renderer_startup_error.log` beside
  it. The log can contain local paths; review it before sharing.

Continue with the [GUI guide](GETTING_STARTED.md), the [CLI guide](CLI.md) or the
[Python vignette](PYTHON.md), or return to the [documentation home](index.md).
