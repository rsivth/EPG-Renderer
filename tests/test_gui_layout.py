from __future__ import annotations

import unittest

from epg_renderer import gui, manual_gui
from epg_renderer.domain import PeakHeightMode


class GuiLayoutRegressionTests(unittest.TestCase):
    def test_main_window_and_selectors_remain_compact(self):
        self.assertLess(gui.MAIN_WINDOW_WIDTH, 820)
        self.assertLessEqual(gui.MAIN_SELECTOR_WIDTH, 34)
        self.assertLess(gui.MAIN_MIN_WIDTH, 760)

    def test_manual_entry_widths_match_expected_information_density(self):
        self.assertLess(manual_gui.MANUAL_WINDOW_WIDTH, 900)
        self.assertLessEqual(manual_gui.MANUAL_KIT_WIDTH, 34)
        self.assertGreater(manual_gui.MANUAL_ALLELE_WIDTH, manual_gui.MANUAL_RFU_WIDTH)
        self.assertLessEqual(manual_gui.MANUAL_RFU_WIDTH, 20)

    def test_rfu_fields_are_only_visible_in_rfu_mode(self):
        self.assertTrue(manual_gui._rfu_fields_visible(PeakHeightMode.RFU.value))
        self.assertFalse(manual_gui._rfu_fields_visible(PeakHeightMode.UNIFORM.value))
        self.assertFalse(manual_gui._rfu_fields_visible("unknown"))


if __name__ == "__main__":
    unittest.main()
