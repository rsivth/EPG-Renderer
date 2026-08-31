from __future__ import annotations

import unittest
from collections import OrderedDict

from epg_renderer import (
    list_kits,
    load_kit,
    render_svg,
)
from epg_renderer.domain import (
    ExportCompatibility,
    KitType,
)
from epg_renderer.kit_workflow import position_sample
from epg_renderer.models import AlleleCall, MarkerCall, SampleCall
from epg_renderer.render_options import SvgRenderOptions

EXPECTED = {
    "GlobalFiler",
    "NGM",
    "NGM Detect",
    "PowerPlex ESI 17 Fast",
    "PowerPlex ESX 17 Fast",
    "PowerPlex Y23",
    "PowerPlex Fusion",
    "Investigator Argus X-12",
    "Identifiler",
    "Investigator ESSplex SE QS",
    "NGM SElect",
    "Yfiler Direct",
    "Yfiler Plus",
    "PowerPlex 35GY",
}


class KitCatalogTests(unittest.TestCase):
    def test_all_requested_kits_are_registered(self):
        self.assertEqual({profile.kit.name for profile in list_kits()}, EXPECTED)
        self.assertEqual(len(tuple(profile.kit.name for profile in list_kits())), 14)

    def test_every_profile_is_valid_and_renders(self):
        for profile in list_kits():
            with self.subTest(kit=profile.kit.name):
                profile.coordinate_model.validate(profile.kit)
                markers = OrderedDict()
                for index, marker in enumerate(profile.kit.markers):
                    markers[marker.name] = MarkerCall(
                        marker.name,
                        marker.dye,
                        (AlleleCall(1, marker.ladder_alleles[0], 100 + index),),
                    )
                positioned = position_sample(SampleCall("S", markers), kit_name=profile.kit.name)
                svg = render_svg(positioned, options=SvgRenderOptions(width=1800))
                self.assertIn('data-kit="' + profile.kit.name + '"', svg)
                self.assertEqual(svg.count('class="called-peak"'), len(profile.kit.markers))

    def test_schema_11_metadata_supports_special_loci(self):
        y23 = load_kit("PowerPlex Y23")
        self.assertIs(y23.kit_type, KitType.Y_STR)
        self.assertEqual(y23.marker_metadata["DYS385a/b"].copy_group, "DYS385")
        argus = load_kit("Investigator Argus X-12")
        self.assertIs(argus.kit_type, KitType.X_STR)
        self.assertEqual(len(argus.linkage_groups), 4)
        ngmd = load_kit("NGM Detect")
        self.assertTrue(ngmd.marker_metadata["IQCS"].is_control)
        self.assertTrue(ngmd.marker_metadata["IQCL"].is_control)

    def test_powerplex_35gy_export_limitation_is_machine_readable(self):
        profile = load_kit("PowerPlex 35GY")
        self.assertIs(profile.export_compatibility, ExportCompatibility.GENE_MARKER)
        self.assertFalse(profile.supports_genemapper_export)
        self.assertTrue(any("GeneMapper" in note for note in profile.notes))
        self.assertEqual(len(profile.kit.channels), 7)

    def test_esi_and_esx_have_same_marker_set_but_different_layout(self):
        esi = load_kit("PowerPlex ESI 17 Fast")
        esx = load_kit("PowerPlex ESX 17 Fast")
        self.assertEqual({m.name for m in esi.kit.markers}, {m.name for m in esx.kit.markers})
        self.assertNotEqual(esi.kit.marker("TH01").dye, esx.kit.marker("TH01").dye)
        self.assertNotEqual(esi.kit.source_marker_order, esx.kit.source_marker_order)

    def test_legitimate_se33_alleles_4_2_and_42_remain_distinct(self):
        profile = load_kit("PowerPlex ESI 17 Fast")
        alleles = profile.kit.marker("SE33").ladder_alleles
        self.assertIn("4.2", alleles)
        self.assertIn("42", alleles)
        self.assertNotEqual(
            profile.coordinate_model.marker("SE33").coordinate("4.2").nominal_bp,
            profile.coordinate_model.marker("SE33").coordinate("42").nominal_bp,
        )

    def test_selected_manual_facts(self):
        self.assertEqual(load_kit("PowerPlex Y23").kit.marker("DYS448").dye, "FL")
        self.assertEqual(load_kit("Yfiler Plus").kit.marker("DYF387S1a/b").dye, "SID")
        self.assertEqual(load_kit("Identifiler").kit.marker("FGA").dye, "PET")
        self.assertEqual(load_kit("Investigator ESSplex SE QS").kit.marker("D18S51").dye, "BTR")
        self.assertEqual(load_kit("PowerPlex Fusion").kit.marker("Penta E").dye, "FL")


if __name__ == "__main__":
    unittest.main()
