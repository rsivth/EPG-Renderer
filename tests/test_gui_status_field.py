"""Regressions for the fixed-height status field of the main GUI window.

Until 0.15.1.dev1 the status line and the review hints were two labels that grew with
their text, while the window height was set once at start. Review hints or a long
output path pushed "Close" and "Create image" below the window edge. Since
0.15.1.dev2 status and hints share one read-only text field with a fixed number of
lines and a scrollbar, so no text changes the window layout.
"""

from __future__ import annotations

import tkinter as tk
import unittest

from epg_renderer import gui

LONG_STATUS = "Image created: /Users/Shared/" + "a_long_folder_name/" * 12 + "sample_epg.png"
MANY_HINTS = tuple(f"D{i}S1 allele {i}: synthetic review hint number {i}" for i in range(1, 21))


def _buttons_bottom(app: gui.EpgRendererApp) -> int:
    bar = app.render_button.master
    return int(bar.winfo_rooty() - app.root.winfo_rooty() + bar.winfo_height())


class DiagnosticsFieldTextTests(unittest.TestCase):
    def test_no_hints_give_no_text(self) -> None:
        self.assertEqual(gui.diagnostics_field_text(()), "")

    def test_first_line_names_the_number_of_hints(self) -> None:
        text = gui.diagnostics_field_text(("first", "second", "third"))
        self.assertTrue(text.startswith("3 review hints. "), text)
        for hint in ("first", "second", "third"):
            self.assertIn(hint, text)

    def test_single_hint_is_singular(self) -> None:
        self.assertTrue(gui.diagnostics_field_text(("only",)).startswith("1 review hint. "))


class StatusFieldWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"No display for a Tk window: {exc}")
        self.addCleanup(self.root.destroy)
        self.app = gui.EpgRendererApp(self.root)
        self.root.update()

    def _show(self, status: str, hints: tuple[str, ...]) -> None:
        self.app.status_var.set(status)
        self.app._show_diagnostics(hints)
        self.root.update()

    def test_long_status_and_many_hints_keep_buttons_inside_the_window(self) -> None:
        height = self.root.winfo_height()
        required = self.root.winfo_reqheight()
        self.assertLessEqual(_buttons_bottom(self.app), height)
        self._show(LONG_STATUS, MANY_HINTS)
        self.assertEqual(self.root.winfo_height(), height)
        self.assertEqual(self.root.winfo_reqheight(), required)
        self.assertLessEqual(_buttons_bottom(self.app), self.root.winfo_height())

    def test_field_has_the_fixed_number_of_lines(self) -> None:
        self.assertEqual(gui.STATUS_FIELD_LINES, 6)
        self.assertEqual(int(self.app.status_text.cget("height")), gui.STATUS_FIELD_LINES)
        self._show(LONG_STATUS, MANY_HINTS)
        self.assertEqual(int(self.app.status_text.cget("height")), gui.STATUS_FIELD_LINES)

    def test_many_hints_are_all_in_the_field_and_can_be_scrolled(self) -> None:
        self._show("Image created: /tmp/x.svg", MANY_HINTS)
        content = self.app.status_text.get("1.0", "end-1c")
        self.assertTrue(content.startswith("Image created: /tmp/x.svg\n"))
        self.assertIn("20 review hints. ", content)
        for hint in MANY_HINTS:
            self.assertIn(hint, content)
        first, last = self.app.status_scrollbar.get()
        self.assertEqual(first, 0.0)
        self.assertLess(last, 1.0)

    def test_status_alone_needs_no_scrolling(self) -> None:
        self._show("File valid. Kit identified unambiguously: NGM.", ())
        content = self.app.status_text.get("1.0", "end-1c")
        self.assertEqual(content, "File valid. Kit identified unambiguously: NGM.")
        self.assertEqual(self.app.status_scrollbar.get(), (0.0, 1.0))

    def test_hints_are_red_and_the_status_is_not(self) -> None:
        self._show("Image created: /tmp/x.svg", ("first",))
        text = self.app.status_text
        self.assertEqual(text.tag_cget(gui.DIAGNOSTICS_TAG, "foreground"), gui.DIAGNOSTICS_COLOR)
        self.assertNotIn(gui.DIAGNOSTICS_TAG, text.tag_names("1.0"))
        self.assertIn(gui.DIAGNOSTICS_TAG, text.tag_names("2.0"))

    def test_field_is_read_only_and_starts_at_the_top_after_an_update(self) -> None:
        self._show("Image created: /tmp/x.svg", MANY_HINTS)
        self.app.status_text.yview_moveto(1.0)
        self._show("File valid.", MANY_HINTS)
        self.assertEqual(str(self.app.status_text.cget("state")), "disabled")
        self.assertEqual(self.app.status_text.yview()[0], 0.0)

    def test_clearing_the_hints_leaves_only_the_status(self) -> None:
        self._show("Image created: /tmp/x.svg", MANY_HINTS)
        self.app._show_diagnostics(())
        self.root.update()
        self.assertEqual(self.app.status_text.get("1.0", "end-1c"), "Image created: /tmp/x.svg")


if __name__ == "__main__":
    unittest.main()
