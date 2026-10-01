"""Regression for the off-ladder hint in the manual-profile dialog.

Since 0.15.0.dev2 manual entries accept ``OL@<allele>``. The dialog previously said
only that numerical off-ladder alleles are accepted when they can be positioned; it
now names the syntax with an example. Kept in a test_gui module because it imports
Tkinter.
"""

from __future__ import annotations

import unittest

from epg_renderer import manual_gui


class ManualOffLadderHintTests(unittest.TestCase):
    def test_dialog_hint_names_the_off_ladder_syntax(self) -> None:
        self.assertIn("OL@", manual_gui.MANUAL_ENTRY_HINT)
        self.assertIn("ladder", manual_gui.MANUAL_ENTRY_HINT)


if __name__ == "__main__":
    unittest.main()
