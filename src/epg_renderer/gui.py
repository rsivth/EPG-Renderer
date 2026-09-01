"""Small Tkinter front end for file-based and manual EPG rendering."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import tkinter as tk
import webbrowser
from collections.abc import Callable, Sequence
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import cast

from .domain import PeakHeightMode
from .gui_workflow import (
    FileInspection,
    choose_output_path_value,
    inspect_genemapper_file,
    suggested_manual_output_path,
    suggested_output_path,
    validated_output_path,
)
from .kit_registry import available_genemapper_kit_names, available_kit_profiles
from .manual_gui import show_manual_profile_dialog
from .manual_profile import ManualProfile
from .render_options import RasterDependencyError, SvgRenderOptions, YellowChannelMode
from .version import __version__
from .workflow import (
    format_diagnostics,
    render_genemapper_epg_report,
    render_manual_epg_report,
)

logger = logging.getLogger(__name__)

DIAGNOSTICS_COLOR = "#C62828"
MAIN_WINDOW_WIDTH = 760
MAIN_MIN_WIDTH = 700
MAIN_SELECTOR_WIDTH = 31


class EpgRendererApp:
    """Single-window, guided EPG rendering interface."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"EPG-Renderer {__version__}")
        self.root.minsize(820, 560)
        self.inspection: FileInspection | None = None
        self.manual_profile: ManualProfile | None = None
        self.input_var = tk.StringVar()
        self.sample_var = tk.StringVar()
        self.kit_var = tk.StringVar()
        self.format_var = tk.StringVar(value="svg")
        self.yellow_var = tk.StringVar(value=YellowChannelMode.YELLOW.value)
        self.output_var = tk.StringVar()
        self.open_var = tk.BooleanVar(value=True)
        self.diagnostics_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(
            value="Choose a GeneMapper export or create a profile manually."
        )
        self._last_suggested_output: str | None = None
        self._build()

    def _build(self) -> None:
        style = ttk.Style()
        style.configure("Title.TLabel", font=("TkDefaultFont", 15, "bold"))
        style.configure("Muted.TLabel", foreground="#555555")
        style.configure("Section.TLabelframe.Label", font=("TkDefaultFont", 10, "bold"))

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        outer = ttk.Frame(self.root, padding=18)
        outer.grid(row=0, column=0, sticky="nsew")
        outer.columnconfigure(0, weight=1)

        header = ttk.Frame(outer)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="EPG-Renderer", style="Title.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            header,
            text=(
                "Create a schematic electropherogram from a GeneMapper export "
                "or a manually entered profile."
            ),
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        input_group = ttk.LabelFrame(
            outer,
            text="1. Input",
            style="Section.TLabelframe",
            padding=(12, 10),
        )
        input_group.grid(row=1, column=0, sticky="ew")
        input_group.columnconfigure(1, weight=1)

        source_buttons = ttk.Frame(input_group)
        source_buttons.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        ttk.Button(
            source_buttons,
            text="Choose GeneMapper file…",
            command=self.choose_input,
        ).pack(side="left", padx=(0, 8))
        self.manual_button = ttk.Button(
            source_buttons,
            text="Create manually…",
            command=self.choose_manual_profile,
        )
        self.manual_button.pack(side="left")

        ttk.Label(input_group, text="Current input").grid(row=1, column=0, sticky="w", padx=(0, 10))
        ttk.Entry(input_group, textvariable=self.input_var, state="readonly").grid(
            row=1, column=1, columnspan=2, sticky="ew"
        )

        ttk.Label(input_group, text="Sample / profile").grid(
            row=2, column=0, sticky="w", padx=(0, 10), pady=(10, 0)
        )
        self.sample_combo = ttk.Combobox(
            input_group,
            textvariable=self.sample_var,
            state="disabled",
            width=MAIN_SELECTOR_WIDTH,
        )
        self.sample_combo.grid(row=2, column=1, sticky="w", pady=(10, 0))
        self.sample_combo.bind("<<ComboboxSelected>>", self._on_sample_selected)

        ttk.Label(input_group, text="Kit").grid(
            row=3, column=0, sticky="w", padx=(0, 10), pady=(8, 0)
        )
        self.kit_combo = ttk.Combobox(
            input_group,
            textvariable=self.kit_var,
            state="disabled",
            values=available_genemapper_kit_names(),
            width=MAIN_SELECTOR_WIDTH,
        )
        self.kit_combo.grid(row=3, column=1, sticky="w", pady=(8, 0))

        output_group = ttk.LabelFrame(
            outer,
            text="2. Output",
            style="Section.TLabelframe",
            padding=(12, 10),
        )
        output_group.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        output_group.columnconfigure(1, weight=1)

        ttk.Label(output_group, text="Image format").grid(row=0, column=0, sticky="w", padx=(0, 10))
        format_frame = ttk.Frame(output_group)
        format_frame.grid(row=0, column=1, sticky="w")
        for text, value in (("SVG", "svg"), ("PNG", "png"), ("JPG", "jpg")):
            ttk.Radiobutton(
                format_frame,
                text=text,
                value=value,
                variable=self.format_var,
                command=self._update_output_suffix,
            ).pack(side="left", padx=(0, 16))

        ttk.Label(output_group, text="Yellow channel").grid(
            row=1, column=0, sticky="w", padx=(0, 10), pady=(8, 0)
        )
        yellow_frame = ttk.Frame(output_group)
        yellow_frame.grid(row=1, column=1, sticky="w", pady=(8, 0))
        ttk.Radiobutton(
            yellow_frame,
            text="Yellow",
            value="yellow",
            variable=self.yellow_var,
        ).pack(side="left", padx=(0, 16))
        ttk.Radiobutton(
            yellow_frame,
            text="Black",
            value="black",
            variable=self.yellow_var,
        ).pack(side="left")

        ttk.Label(output_group, text="Output file").grid(
            row=2, column=0, sticky="w", padx=(0, 10), pady=(10, 0)
        )
        ttk.Entry(output_group, textvariable=self.output_var).grid(
            row=2, column=1, sticky="ew", pady=(10, 0)
        )
        ttk.Button(output_group, text="Save as…", command=self.choose_output).grid(
            row=2, column=2, sticky="e", padx=(8, 0), pady=(10, 0)
        )
        ttk.Checkbutton(
            output_group,
            text="Open image after creation",
            variable=self.open_var,
        ).grid(row=3, column=1, columnspan=2, sticky="w", pady=(8, 0))

        status_group = ttk.LabelFrame(
            outer,
            text="Status",
            style="Section.TLabelframe",
            padding=(12, 8),
        )
        status_group.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        status_group.columnconfigure(0, weight=1)
        self.status_label = ttk.Label(
            status_group,
            textvariable=self.status_var,
            justify="left",
            anchor="w",
        )
        self.status_label.grid(row=0, column=0, sticky="ew")
        self.status_label.bind("<Configure>", self._resize_status_wrap)
        self.diagnostics_label = tk.Label(
            status_group,
            textvariable=self.diagnostics_var,
            justify="left",
            anchor="w",
            foreground=DIAGNOSTICS_COLOR,
        )
        self.diagnostics_label.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        self.diagnostics_label.bind("<Configure>", self._resize_diagnostics_wrap)
        self.diagnostics_label.grid_remove()

        button_bar = ttk.Frame(outer)
        button_bar.grid(row=4, column=0, sticky="e", pady=(14, 0))
        ttk.Button(button_bar, text="Close", command=self.root.destroy).pack(
            side="left", padx=(0, 8)
        )
        self.render_button = ttk.Button(
            button_bar,
            text="Create image",
            command=self.create_image,
            state="disabled",
        )
        self.render_button.pack(side="left")

        self.root.bind("<Escape>", lambda _event: self.root.destroy())
        self.root.update_idletasks()
        preferred_height = max(560, self.root.winfo_reqheight())
        self.root.minsize(MAIN_MIN_WIDTH, preferred_height)
        self.root.geometry(f"{MAIN_WINDOW_WIDTH}x{preferred_height}")

    def _resize_diagnostics_wrap(self, event: tk.Event[tk.Misc]) -> None:
        """Keep diagnostic text readable when the main window is resized."""

        self.diagnostics_label.configure(wraplength=max(280, event.width - 4))

    def _show_diagnostics(self, messages: Sequence[str]) -> None:
        """Display every diagnostic prominently, or hide the area when there is none."""

        block = format_diagnostics(messages)
        self.diagnostics_var.set(block)
        if block:
            self.diagnostics_label.grid()
        else:
            self.diagnostics_label.grid_remove()

    def _resize_status_wrap(self, event: tk.Event[tk.Misc]) -> None:
        """Keep status text readable when the main window is resized."""

        self.status_label.configure(wraplength=max(280, event.width - 4))

    def choose_input(self) -> None:
        """Select and inspect a GeneMapper input file."""

        selected = filedialog.askopenfilename(
            title="Select GeneMapper genotype export",
            filetypes=(("GeneMapper export", "*.csv *.tsv *.txt"), ("All files", "*.*")),
        )
        if not selected:
            return
        self.input_var.set(selected)
        self.status_var.set("Checking file…")
        self.root.update_idletasks()
        try:
            inspection = inspect_genemapper_file(selected)
        except (OSError, ValueError) as exc:
            self._reject_input(str(exc))
            return
        except Exception:
            logger.exception("Unexpected error while inspecting %s", selected)
            self._reject_input("An unexpected internal error occurred while checking the file.")
            return
        self.inspection = inspection
        self.manual_profile = None
        self.manual_button.configure(text="Create manually…")
        ids = tuple(item.sample_id for item in inspection.samples)
        self.sample_combo.configure(values=ids, state="readonly" if len(ids) > 1 else "disabled")
        self.sample_var.set(ids[0])
        self._update_kit_state()
        self._suggest_output(force=True)

    def choose_manual_profile(self) -> None:
        """Create or edit a manual kit-aware profile in a modal dialog."""

        profile = show_manual_profile_dialog(self.root, self.manual_profile)
        if profile is None:
            return
        self.manual_profile = profile
        self.inspection = None
        self.input_var.set(f"Manual profile: {profile.name}")
        self.sample_var.set(profile.name)
        self.sample_combo.configure(values=(profile.name,), state="disabled")
        self.kit_var.set(profile.kit_name)
        self.kit_combo.configure(values=(profile.kit_name,), state="disabled")
        self.manual_button.configure(text="Edit manual profile…")
        mode_text = (
            "user-entered RFU heights"
            if profile.height_mode is PeakHeightMode.RFU
            else "uniform non-quantitative peak heights"
        )
        self.status_var.set(f"Manual profile valid: {profile.kit_name}; {mode_text}.")
        self.render_button.configure(state="normal")
        self._suggest_output(force=True)

    def _reject_input(self, message: str) -> None:
        self.inspection = None
        self.manual_profile = None
        self.sample_combo.configure(state="disabled", values=())
        self.kit_combo.configure(state="disabled")
        self.render_button.configure(state="disabled")
        self.status_var.set(f"The file is not usable: {message}")
        messagebox.showerror("Invalid GeneMapper file", message, parent=self.root)

    def _update_kit_state(self) -> None:
        if self.inspection is None or not self.sample_var.get():
            return
        decision = self.inspection.sample(self.sample_var.get())
        if decision.resolved_kit_name:
            self.kit_var.set(decision.resolved_kit_name)
            self.kit_combo.configure(state="disabled", values=(decision.resolved_kit_name,))
            self.status_var.set(
                f"File valid. Kit identified unambiguously: {decision.resolved_kit_name}."
            )
            self.render_button.configure(state="normal")
        elif decision.compatible_kit_names:
            self.kit_var.set("")
            self.kit_combo.configure(state="readonly", values=decision.compatible_kit_names)
            self.status_var.set(
                "File valid, but kit assignment is not unambiguous. "
                "Select the kit before creating the image."
            )
            self.render_button.configure(state="normal")
        else:
            self.kit_var.set("")
            self.kit_combo.configure(state="disabled", values=())
            self.status_var.set("No GeneMapper-compatible bundled kit matches the selected sample.")
            self.render_button.configure(state="disabled")

    def _on_sample_selected(self, _event: object | None = None) -> None:
        self._update_kit_state()
        self._suggest_output()

    def _suggest_output(self, *, force: bool = False) -> None:
        if self.manual_profile is not None:
            suggestion = str(
                suggested_manual_output_path(
                    self.manual_profile.name,
                    self.format_var.get(),
                    input_path=self.input_var.get() or None,
                )
            )
        elif self.inspection is not None and self.input_var.get():
            suggestion = str(
                suggested_output_path(
                    self.input_var.get(),
                    self.sample_var.get(),
                    self.format_var.get(),
                )
            )
        else:
            return
        selected = choose_output_path_value(
            self.output_var.get(),
            self._last_suggested_output,
            suggestion,
            force=force,
        )
        if selected != self.output_var.get():
            self.output_var.set(selected)
        self._last_suggested_output = suggestion

    def _update_output_suffix(self) -> None:
        value = self.output_var.get()
        if value == self._last_suggested_output:
            self._suggest_output(force=True)
            return
        if value:
            self.output_var.set(str(Path(value).with_suffix("." + self.format_var.get())))
        if self.manual_profile is not None or self.inspection is not None:
            current = self.output_var.get()
            self._suggest_output()
            self.output_var.set(current)

    def choose_output(self) -> None:
        """Select an output path while preserving an explicit user choice."""

        fmt = self.format_var.get()
        selected = filedialog.asksaveasfilename(
            title="Save electropherogram",
            defaultextension="." + fmt,
            filetypes=((fmt.upper(), "*." + fmt), ("All files", "*.*")),
            initialfile=Path(self.output_var.get()).name if self.output_var.get() else None,
        )
        if selected:
            self.output_var.set(selected)

    def create_image(self) -> None:
        """Validate the form, render the selected input, and report the outcome."""

        if self.manual_profile is None and self.inspection is None:
            messagebox.showwarning(
                "No input",
                "Choose a valid GeneMapper file or create a manual profile first.",
                parent=self.root,
            )
            return
        kit = self.kit_var.get().strip()
        if not kit:
            messagebox.showwarning(
                "Kit required", "Select the amplification kit.", parent=self.root
            )
            return
        try:
            output = validated_output_path(self.output_var.get(), self.format_var.get())
        except ValueError as exc:
            messagebox.showwarning("Output file required", str(exc), parent=self.root)
            return
        self.output_var.set(str(output))
        options = SvgRenderOptions(yellow_channel_mode=self.yellow_var.get())
        self._show_diagnostics(())
        try:
            if self.manual_profile is not None:
                report = render_manual_epg_report(self.manual_profile, output, options=options)
            else:
                report = render_genemapper_epg_report(
                    self.input_var.get(),
                    output,
                    sample_id=self.sample_var.get(),
                    kit_name=kit,
                    options=options,
                )
        except RasterDependencyError as exc:
            messagebox.showerror("Raster support missing", str(exc), parent=self.root)
            return
        except (OSError, ValueError) as exc:
            messagebox.showerror("Could not create image", str(exc), parent=self.root)
            return
        except Exception:
            logger.exception("Unexpected error while rendering an EPG")
            messagebox.showerror(
                "Could not create image",
                "An unexpected internal error occurred. See the application log for details.",
                parent=self.root,
            )
            return
        self.status_var.set(f"Image created: {output}")
        self._show_diagnostics(report.messages())
        if report.has_omitted_peaks:
            messagebox.showwarning(
                "Image is incomplete",
                "The image was saved, but at least one called peak could not be placed "
                "and is missing from it. The status area lists every affected peak.",
                parent=self.root,
            )
        else:
            messagebox.showinfo(
                "EPG created", f"The image was saved to:\n{output}", parent=self.root
            )
        if self.open_var.get():
            _open_output(output)


def _open_output(path: Path) -> None:
    resolved = path.resolve()
    if sys.platform.startswith("win"):
        startfile = cast(Callable[[Path], object], os.startfile)
        startfile(resolved)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(resolved)])
    else:
        if not webbrowser.open(resolved.as_uri()):
            subprocess.Popen(["xdg-open", str(resolved)])


def _check_runtime() -> int:
    profiles = available_kit_profiles()
    if not profiles:
        raise RuntimeError("No bundled kit resources were found.")

    root = tk.Tk()
    try:
        root.withdraw()
        EpgRendererApp(root)
        root.update_idletasks()
    finally:
        root.destroy()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Check or start the Tkinter application and return a process status."""

    arguments = tuple(sys.argv[1:] if argv is None else argv)
    if arguments == ("--check",):
        return _check_runtime()
    if arguments:
        return 2

    root = tk.Tk()
    EpgRendererApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
