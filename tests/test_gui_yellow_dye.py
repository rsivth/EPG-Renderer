"""Regressions for the yellow-dye choice in the main GUI window.

Until 0.14.0.dev5 the choice read "Yellow channel: Yellow / Black". It did not say what
the setting changes or why anyone would pick black. The label now names the displayed
colour of the yellow dye and the black option states its purpose.
"""

from __future__ import annotations

import unittest

from epg_renderer import gui
from epg_renderer.render_options import YellowChannelMode


class YellowDyeChoiceTests(unittest.TestCase):
    def test_label_says_how_the_yellow_dye_is_shown(self) -> None:
        self.assertEqual(gui.YELLOW_DYE_LABEL, "Yellow dye shown as")

    def test_black_option_states_its_purpose(self) -> None:
        texts = [text for text, _mode in gui.YELLOW_DYE_CHOICES]
        self.assertEqual(texts, ["Yellow", "Black (better contrast)"])

    def test_choices_cover_every_render_mode_once_with_yellow_first(self) -> None:
        modes = [mode for _text, mode in gui.YELLOW_DYE_CHOICES]
        self.assertEqual(modes, [YellowChannelMode.YELLOW, YellowChannelMode.BLACK])
        self.assertEqual(set(modes), set(YellowChannelMode))


if __name__ == "__main__":
    unittest.main()
