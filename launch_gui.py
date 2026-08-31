"""Start the EPG-Renderer GUI directly from an unpacked source archive."""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parent


def _prepare_import_path(root: Path) -> None:
    source_directory = root / "src"
    package_directory = source_directory / "epg_renderer"
    if not package_directory.is_dir():
        raise RuntimeError(
            "The folder 'src\\epg_renderer' is missing. "
            "Extract the complete EPG-Renderer ZIP before starting the GUI."
        )
    sys.path.insert(0, str(source_directory))


def _write_error_log(root: Path) -> Path:
    log_path = root / "EPG-Renderer_startup_error.log"
    log_path.write_text(traceback.format_exc(), encoding="utf-8")
    return log_path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def _show_error_message(message: str) -> None:
    """Report startup failures without requiring a visible console window."""

    stream = sys.stderr
    if stream is not None:
        print(f"\nEPG-Renderer could not start.\n\n{message}\n", file=stream)
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, message, "EPG-Renderer", 0x10)
    except (AttributeError, OSError):
        pass


def main() -> int:
    """Launch the local GUI without installing the package."""

    root = _project_root()
    try:
        _prepare_import_path(root)
        import tkinter  # noqa: F401

        from epg_renderer.gui import main as gui_main
        from epg_renderer.version import __version__

        if _parse_args().check:
            print(f"EPG-Renderer {__version__}: offline GUI launcher is ready.")
            return 0
        return gui_main()
    except ModuleNotFoundError as exc:
        if exc.name == "tkinter":
            message = (
                "This Python installation does not include Tkinter, which is required for the GUI.\n"
                "Use a standard Windows Python installation with the optional Tcl/Tk component."
            )
        else:
            message = f"A required local module could not be loaded: {exc}"
        _show_error_message(message)
        return 2
    except Exception as exc:  # noqa: BLE001 - final process boundary records startup failures
        try:
            log_path = _write_error_log(root)
            log_note = f"\n\nTechnical details were written to:\n{log_path}"
        except OSError:
            log_note = "\n\nThe technical error log could not be written."
        _show_error_message(f"{exc}{log_note}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
