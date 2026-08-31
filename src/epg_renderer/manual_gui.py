"""Tkinter dialog for creating validated manual electropherogram profiles."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from .domain import PeakHeightMode
from .kit_registry import available_kit_names
from .manual_profile import (
    ManualMarkerEntry,
    ManualProfile,
    ManualProfileError,
    build_manual_profile,
    editable_marker_names,
    parse_manual_marker_text,
)
from .rfu import MAX_RFU

MANUAL_WINDOW_WIDTH = 720
MANUAL_MIN_WIDTH = 660
MANUAL_NAME_WIDTH = 36
MANUAL_KIT_WIDTH = 34
MANUAL_ALLELE_WIDTH = 30
MANUAL_RFU_WIDTH = 20

_WindowParent = tk.Tk | tk.Toplevel


def _rfu_fields_visible(mode_value: str) -> bool:
    """Return whether RFU-specific entry widgets should be visible."""

    return mode_value == PeakHeightMode.RFU.value


class ManualProfileDialog:
    """Modal editor for one kit-aware manual profile."""

    def __init__(self, parent: _WindowParent, initial: ManualProfile | None = None):
        self.parent = parent
        self.initial = initial
        self.result: ManualProfile | None = None
        self.window = tk.Toplevel(parent)
        self.window.title("Manual profile")
        self.window.minsize(MANUAL_MIN_WIDTH, 560)
        self.window.geometry(f"{MANUAL_WINDOW_WIDTH}x640")
        self.window.transient(parent)
        self.window.protocol("WM_DELETE_WINDOW", self._cancel)
        self.name_var = tk.StringVar(value=initial.name if initial else "Manual profile")
        self.kit_var = tk.StringVar(value=initial.kit_name if initial else available_kit_names()[0])
        self.height_mode_var = tk.StringVar(
            value=(initial.height_mode if initial else PeakHeightMode.UNIFORM).value
        )
        self._current_kit = self.kit_var.get()
        self._allele_vars: dict[str, tk.StringVar] = {}
        self._height_vars: dict[str, tk.StringVar] = {}
        self._height_entries: dict[str, ttk.Entry] = {}
        self._initial_entries = (
            {entry.marker: entry for entry in initial.markers} if initial else {}
        )
        self._build()
        self._rebuild_marker_rows()
        self._apply_height_mode()
        self.window.bind("<Escape>", lambda _event: self._cancel())
        self.window.bind("<Control-Return>", lambda _event: self._submit())
        self.window.grab_set()
        self.name_entry.focus_set()
        if initial is None:
            self.name_entry.selection_range(0, "end")

    def show(self) -> ManualProfile | None:
        """Block until the dialog closes and return its validated result."""

        self.window.wait_window()
        return self.result

    def _build(self) -> None:
        style = ttk.Style()
        style.configure("DialogTitle.TLabel", font=("TkDefaultFont", 13, "bold"))
        style.configure("DialogMuted.TLabel", foreground="#555555")
        style.configure("DialogSection.TLabelframe.Label", font=("TkDefaultFont", 10, "bold"))
        style.configure("TableHeader.TLabel", font=("TkDefaultFont", 9, "bold"))

        outer = ttk.Frame(self.window, padding=16)
        outer.grid(row=0, column=0, sticky="nsew")
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(3, weight=1)

        ttk.Label(
            outer,
            text="Create a manual schematic profile",
            style="DialogTitle.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            outer,
            text=(
                "Enter one or more alleles per marker. Separate multiple values with commas, "
                "semicolons, or spaces; empty markers are allowed. In RFU mode, enter one "
                f"whole-number height from 1 to {MAX_RFU:,} per allele."
            ),
            style="DialogMuted.TLabel",
            wraplength=670,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(3, 12))

        settings = ttk.LabelFrame(
            outer,
            text="Profile settings",
            style="DialogSection.TLabelframe",
            padding=(12, 10),
        )
        settings.grid(row=2, column=0, sticky="ew")
        settings.columnconfigure(1, weight=1)

        ttk.Label(settings, text="Profile name").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.name_entry = ttk.Entry(settings, textvariable=self.name_var, width=MANUAL_NAME_WIDTH)
        self.name_entry.grid(row=0, column=1, sticky="w")

        ttk.Label(settings, text="Kit").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=(8, 0))
        self.kit_combo = ttk.Combobox(
            settings,
            textvariable=self.kit_var,
            values=available_kit_names(),
            state="readonly",
            width=MANUAL_KIT_WIDTH,
        )
        self.kit_combo.grid(row=1, column=1, sticky="w", pady=(8, 0))
        self.kit_combo.bind("<<ComboboxSelected>>", self._on_kit_selected)

        ttk.Label(settings, text="Peak heights").grid(
            row=2, column=0, sticky="nw", padx=(0, 10), pady=(9, 0)
        )
        height_frame = ttk.Frame(settings)
        height_frame.grid(row=2, column=1, sticky="w", pady=(8, 0))
        ttk.Radiobutton(
            height_frame,
            text="Uniform schematic heights (no RFU axis)",
            value=PeakHeightMode.UNIFORM.value,
            variable=self.height_mode_var,
            command=self._apply_height_mode,
        ).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(
            height_frame,
            text="Enter RFU heights",
            value=PeakHeightMode.RFU.value,
            variable=self.height_mode_var,
            command=self._apply_height_mode,
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))

        marker_group = ttk.LabelFrame(
            outer,
            text="Marker entries",
            style="DialogSection.TLabelframe",
            padding=(10, 8),
        )
        marker_group.grid(row=3, column=0, sticky="nsew", pady=(12, 0))
        marker_group.columnconfigure(0, weight=1)
        marker_group.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(marker_group, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(marker_group, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.rows_frame = ttk.Frame(self.canvas, padding=(2, 2, 8, 2))
        self.rows_window = self.canvas.create_window((0, 0), window=self.rows_frame, anchor="nw")
        self.rows_frame.bind("<Configure>", self._update_scroll_region)
        self.canvas.bind("<Configure>", self._resize_rows_frame)
        self.canvas.bind("<Enter>", self._bind_mousewheel)
        self.canvas.bind("<Leave>", self._unbind_mousewheel)

        ttk.Label(
            outer,
            text=(
                "Technical kit controls are omitted. Numerical off-ladder alleles are accepted "
                "only when the bundled coordinate model can position them safely."
            ),
            style="DialogMuted.TLabel",
            wraplength=670,
            justify="left",
        ).grid(row=4, column=0, sticky="w", pady=(9, 0))

        buttons = ttk.Frame(outer)
        buttons.grid(row=5, column=0, sticky="e", pady=(14, 0))
        ttk.Button(buttons, text="Cancel", command=self._cancel).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Use profile", command=self._submit).pack(side="left")

    def _rebuild_marker_rows(self) -> None:
        for child in self.rows_frame.winfo_children():
            child.destroy()
        self._allele_vars.clear()
        self._height_vars.clear()
        self._height_entries.clear()

        marker_names = editable_marker_names(self.kit_var.get())
        marker_width = max(14, max((len(name) for name in marker_names), default=14))
        self.rows_frame.columnconfigure(0, minsize=marker_width * 8)
        self.rows_frame.columnconfigure(1, minsize=250)
        self.rows_frame.columnconfigure(2, minsize=170)

        ttk.Label(
            self.rows_frame,
            text="Marker",
            style="TableHeader.TLabel",
        ).grid(row=0, column=0, sticky="w", padx=(0, 12), pady=(0, 5))
        ttk.Label(
            self.rows_frame,
            text="Alleles",
            style="TableHeader.TLabel",
        ).grid(row=0, column=1, sticky="w", padx=(0, 12), pady=(0, 5))
        self.height_header = ttk.Label(
            self.rows_frame,
            text=f"RFU heights (1–{MAX_RFU:,})",
            style="TableHeader.TLabel",
        )
        self.height_header.grid(row=0, column=2, sticky="w", pady=(0, 5))

        for row, marker in enumerate(marker_names, start=1):
            initial = self._initial_entries.get(marker)
            alleles = ", ".join(initial.alleles) if initial else ""
            heights = (
                ", ".join(str(value) for value in initial.heights)
                if initial and initial.heights is not None
                else ""
            )
            allele_var = tk.StringVar(value=alleles)
            height_var = tk.StringVar(value=heights)
            self._allele_vars[marker] = allele_var
            self._height_vars[marker] = height_var
            ttk.Label(self.rows_frame, text=marker, width=marker_width).grid(
                row=row, column=0, sticky="w", padx=(0, 12), pady=2
            )
            ttk.Entry(
                self.rows_frame,
                textvariable=allele_var,
                width=MANUAL_ALLELE_WIDTH,
            ).grid(row=row, column=1, sticky="w", padx=(0, 12), pady=2)
            height_entry = ttk.Entry(
                self.rows_frame,
                textvariable=height_var,
                width=MANUAL_RFU_WIDTH,
            )
            height_entry.grid(row=row, column=2, sticky="w", pady=2)
            self._height_entries[marker] = height_entry
        self._initial_entries = {}
        self._apply_height_mode()

    def _on_kit_selected(self, _event: object | None = None) -> None:
        selected = self.kit_var.get()
        if selected == self._current_kit:
            return
        has_values = any(value.get().strip() for value in self._allele_vars.values())
        if has_values and not messagebox.askokcancel(
            "Change kit",
            "Changing the kit discards all current marker entries. Continue?",
            parent=self.window,
        ):
            self.kit_var.set(self._current_kit)
            return
        self._current_kit = selected
        self._initial_entries = {}
        self._rebuild_marker_rows()

    def _apply_height_mode(self) -> None:
        show_heights = _rfu_fields_visible(self.height_mode_var.get())
        if not hasattr(self, "height_header"):
            return
        if show_heights:
            self.height_header.grid()
            for entry in self._height_entries.values():
                entry.grid()
                entry.configure(state="normal")
        else:
            self.height_header.grid_remove()
            for entry in self._height_entries.values():
                entry.configure(state="disabled")
                entry.grid_remove()

    def _submit(self) -> None:
        try:
            mode = PeakHeightMode(self.height_mode_var.get())
            entries: dict[str, ManualMarkerEntry] = {}
            for marker in editable_marker_names(self.kit_var.get()):
                height_text = self._height_vars[marker].get() if mode is PeakHeightMode.RFU else ""
                entry = parse_manual_marker_text(
                    marker,
                    self._allele_vars[marker].get(),
                    height_text,
                    mode,
                )
                if entry is not None:
                    entries[marker] = entry
            self.result = build_manual_profile(
                self.name_var.get(),
                self.kit_var.get(),
                entries,
                height_mode=mode,
            )
        except (ManualProfileError, ValueError) as exc:
            messagebox.showerror("Invalid manual profile", str(exc), parent=self.window)
            return
        self.window.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.window.destroy()

    def _update_scroll_region(self, _event: object | None = None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _resize_rows_frame(self, event: tk.Event[tk.Misc]) -> None:
        requested = self.rows_frame.winfo_reqwidth()
        self.canvas.itemconfigure(self.rows_window, width=max(event.width, requested))

    def _bind_mousewheel(self, _event: object | None = None) -> None:
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>", self._on_mousewheel)
        self.canvas.bind_all("<Button-5>", self._on_mousewheel)

    def _unbind_mousewheel(self, _event: object | None = None) -> None:
        self.canvas.unbind_all("<MouseWheel>")
        self.canvas.unbind_all("<Button-4>")
        self.canvas.unbind_all("<Button-5>")

    def _on_mousewheel(self, event: tk.Event[tk.Misc]) -> None:
        if getattr(event, "num", None) == 4:
            direction = -1
        elif getattr(event, "num", None) == 5:
            direction = 1
        else:
            delta = getattr(event, "delta", 0)
            direction = -1 if delta > 0 else 1
        self.canvas.yview_scroll(direction, "units")


def show_manual_profile_dialog(
    parent: _WindowParent,
    initial: ManualProfile | None = None,
) -> ManualProfile | None:
    """Open the modal manual-profile editor and return the accepted profile."""

    return ManualProfileDialog(parent, initial).show()


__all__ = ["ManualProfileDialog", "show_manual_profile_dialog"]
