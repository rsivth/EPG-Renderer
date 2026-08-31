import unittest

from epg_renderer import load_kit


class GlobalFilerDefinitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kit = load_kit("GlobalFiler").kit
        cls.profile = load_kit("GlobalFiler")

    def test_definition_is_constructed_valid(self):
        self.assertEqual(self.kit.name, "GlobalFiler")

    def test_has_five_sample_dye_channels(self):
        self.assertEqual(
            [channel.code for channel in self.kit.channels], ["FAM", "VIC", "NED", "TAZ", "SID"]
        )

    def test_has_24_markers(self):
        self.assertEqual(len(self.kit.markers), 24)

    def test_expected_source_order(self):
        self.assertEqual(
            self.kit.source_marker_order,
            (
                "D3S1358",
                "vWA",
                "D16S539",
                "CSF1PO",
                "TPOX",
                "Yindel",
                "Amelogenin",
                "D8S1179",
                "D21S11",
                "D18S51",
                "DYS391",
                "D2S441",
                "D19S433",
                "TH01",
                "FGA",
                "D22S1045",
                "D5S818",
                "D13S317",
                "D7S820",
                "SE33",
                "D10S1248",
                "D1S1656",
                "D12S391",
                "D2S1338",
            ),
        )

    def test_marker_aliases(self):
        self.assertEqual(self.kit.canonical_marker("AM"), "Amelogenin")
        self.assertEqual(self.kit.canonical_marker("amel"), "Amelogenin")
        self.assertEqual(self.kit.canonical_marker("Y indel"), "Yindel")

    def test_unknown_marker_is_not_silently_accepted(self):
        self.assertIsNone(self.kit.canonical_marker("IQCS"))

    def test_microvariants_are_preserved_as_strings(self):
        self.assertIn("9.3", self.kit.marker("TH01").ladder_alleles)
        self.assertIn("25.2", self.kit.marker("SE33").ladder_alleles)
        self.assertIn("14.3", self.kit.marker("D1S1656").ladder_alleles)

    def test_sex_marker_alleles_are_strings(self):
        self.assertEqual(self.kit.marker("AM").ladder_alleles, ("X", "Y"))

    def test_kit_alias_resolution(self):
        self.assertIs(load_kit("GFI").kit, self.kit)
        self.assertIs(load_kit("GlobalFiler PCR Amplification Kit").kit, self.kit)

    def test_dye_alias_normalization(self):
        aliases = {
            "6-FAM": "FAM",
            "FAM": "FAM",
            "Blue": "FAM",
            "VIC": "VIC",
            "Green": "VIC",
            "NED": "NED",
            "Yellow": "NED",
            "TAZ": "TAZ",
            "Red": "TAZ",
            "SID": "SID",
            "Purple": "SID",
        }
        for source, expected in aliases.items():
            with self.subTest(source=source):
                self.assertEqual(self.profile.normalize_dye(source), expected)

    def test_unknown_dye_returns_none(self):
        self.assertIsNone(self.profile.normalize_dye("LIZ"))


class KitDefinitionValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.kit = load_kit("GlobalFiler").kit

    def test_duplicate_channel_codes_are_rejected(self) -> None:
        from dataclasses import replace

        with self.assertRaisesRegex(ValueError, "Duplicate dye-channel"):
            replace(self.kit, channels=(*self.kit.channels, self.kit.channels[0]))

    def test_empty_and_duplicate_ladder_alleles_are_rejected(self) -> None:
        from dataclasses import replace

        marker = self.kit.markers[0]
        for ladder, message in (((), "empty allelic ladder"), (("15", "15"), "duplicate ladder")):
            with self.subTest(ladder=ladder), self.assertRaisesRegex(ValueError, message):
                invalid_marker = replace(marker, ladder_alleles=ladder)
                replace(self.kit, markers=(invalid_marker, *self.kit.markers[1:]))

    def test_marker_lookup_rejects_unknown_name(self) -> None:
        with self.assertRaises(KeyError):
            self.kit.marker("not-a-marker")
