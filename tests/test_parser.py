from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from epg_renderer import load_project
from epg_renderer.parser import (
    DuplicateHeaderError,
    DuplicateMarkerError,
    GeneMapperParserError,
    MissingRequiredColumnError,
    NumericConversionError,
)

FIXTURES = Path(__file__).with_name("fixtures")


class ParserTests(unittest.TestCase):
    def _write(self, text: str, *, encoding: str = "utf-8", suffix: str = ".csv") -> Path:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temporary:
            path = Path(temporary.name)
        path.write_text(text, encoding=encoding)
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def test_parses_globalfiler_tsv_and_preserves_order(self):
        project = load_project(FIXTURES / "globalfiler_minimal.tsv")
        self.assertEqual(project.sample_ids, ("S1",))
        sample = project.sample("S1")
        self.assertEqual(next(iter(sample.markers)), "D3S1358")
        self.assertEqual(tuple(sample.markers)[-1], "D2S1338")
        self.assertEqual(sample.markers["TH01"].alleles[1].allele, "9.3")
        self.assertEqual(sample.markers["TH01"].alleles[1].height, 750)

    def test_detects_comma_delimiter(self):
        path = self._write("Sample Name,Marker,Dye,Allele 1,Height 1\nS,D3S1358,FAM,15,100\n")
        self.assertEqual(load_project(path).delimiter, ",")

    def test_detects_semicolon_delimiter(self):
        path = self._write("Sample Name;Marker;Dye;Allele 1;Height 1\nS;D3S1358;FAM;15;100\n")
        self.assertEqual(load_project(path).delimiter, ";")

    def test_reads_utf8_bom(self):
        path = self._write(
            "Sample Name\tMarker\tDye\tAllele 1\tHeight 1\nS\tD3S1358\tFAM\t15\t100\n",
            encoding="utf-8-sig",
        )
        project = load_project(path)
        self.assertEqual(project.sample_ids, ("S",))

    def test_reads_cp1252(self):
        path = self._write(
            "Sample Name\tMarker\tDye\tAllele 1\tHeight 1\nPröbe\tD3S1358\tFAM\t15\t100\n",
            encoding="cp1252",
        )
        self.assertEqual(load_project(path).sample_ids, ("Pröbe",))

    def test_multiple_samples(self):
        path = self._write(
            "Sample Name\tMarker\tDye\tAllele 1\tHeight 1\nS1\tD3S1358\tFAM\t15\t100\nS2\tD3S1358\tFAM\t16\t200\n"
        )
        self.assertEqual(load_project(path).sample_ids, ("S1", "S2"))

    def test_supports_more_than_two_called_alleles(self):
        path = self._write(
            "Sample Name\tMarker\tDye\tAllele 1\tHeight 1\tAllele 2\tHeight 2\tAllele 3\tHeight 3\nS\tD3S1358\tFAM\t15\t100\t16\t90\t17\t80\n"
        )
        marker = load_project(path).sample("S").markers["D3S1358"]
        self.assertEqual([call.allele for call in marker.alleles], ["15", "16", "17"])

    def test_empty_allele_and_height_pair_is_ignored(self):
        path = self._write(
            "Sample Name\tMarker\tDye\tAllele 1\tHeight 1\tAllele 2\tHeight 2\nS\tTPOX\tFAM\t8\t100\t\t\n"
        )
        marker = load_project(path).sample("S").markers["TPOX"]
        self.assertEqual(len(marker.alleles), 1)

    def test_rejects_height_without_allele(self):
        path = self._write("Sample Name\tMarker\tDye\tAllele 1\tHeight 1\nS\tTPOX\tFAM\t\t100\n")
        with self.assertRaises(GeneMapperParserError):
            load_project(path)

    def test_rejects_allele_without_height_by_default(self):
        path = self._write("Sample Name\tMarker\tDye\tAllele 1\tHeight 1\nS\tTPOX\tFAM\t8\t\n")
        with self.assertRaises(GeneMapperParserError):
            load_project(path)

    def test_rejects_noninteger_height(self):
        path = self._write("Sample Name\tMarker\tDye\tAllele 1\tHeight 1\nS\tTPOX\tFAM\t8\t100.5\n")
        with self.assertRaises(NumericConversionError):
            load_project(path)

    def test_rejects_negative_height(self):
        path = self._write("Sample Name\tMarker\tDye\tAllele 1\tHeight 1\nS\tTPOX\tFAM\t8\t-1\n")
        with self.assertRaises(NumericConversionError):
            load_project(path)

    def test_accepts_missing_dye_column_as_absent_evidence(self):
        path = self._write("Sample Name\tMarker\tAllele 1\tHeight 1\nS\tTPOX\t8\t100\n")
        marker = load_project(path).sample("S").markers["TPOX"]
        self.assertIsNone(marker.dye)

    def test_rejects_missing_allele_columns(self):
        path = self._write("Sample Name\tMarker\tDye\tHeight 1\nS\tTPOX\tFAM\t100\n")
        with self.assertRaises(MissingRequiredColumnError):
            load_project(path)

    def test_rejects_duplicate_headers_case_insensitively(self):
        path = self._write(
            "Sample Name\tMarker\tDye\tAllele 1\tallele 1\tHeight 1\nS\tTPOX\tFAM\t8\t8\t100\n"
        )
        with self.assertRaises(DuplicateHeaderError):
            load_project(path)

    def test_rejects_duplicate_marker_within_sample(self):
        path = self._write(
            "Sample Name\tMarker\tDye\tAllele 1\tHeight 1\nS\tTPOX\tFAM\t8\t100\nS\tTPOX\tFAM\t9\t90\n"
        )
        with self.assertRaises(DuplicateMarkerError):
            load_project(path)

    def test_rejects_empty_sample_identifier(self):
        path = self._write("Sample Name\tMarker\tDye\tAllele 1\tHeight 1\n\tTPOX\tFAM\t8\t100\n")
        with self.assertRaises(GeneMapperParserError):
            load_project(path)

    def test_rejects_empty_marker(self):
        path = self._write("Sample Name\tMarker\tDye\tAllele 1\tHeight 1\nS\t\tFAM\t8\t100\n")
        with self.assertRaises(GeneMapperParserError):
            load_project(path)

    def test_accepts_empty_dye_as_absent_evidence(self):
        path = self._write("Sample Name\tMarker\tDye\tAllele 1\tHeight 1\nS\tTPOX\t\t8\t100\n")
        marker = load_project(path).sample("S").markers["TPOX"]
        self.assertIsNone(marker.dye)

    def test_ignores_only_empty_trailing_unnamed_columns(self):
        path = self._write("Sample Name\tMarker\tAllele 1\tHeight 1\t\nS\tTPOX\t8\t100\t\n")
        project = load_project(path)
        self.assertEqual(project.header, ("Sample Name", "Marker", "Allele 1", "Height 1"))
        self.assertIn("Ignored 1 empty unnamed trailing column", project.warnings[0])

    def test_rejects_data_in_unnamed_trailing_column(self):
        path = self._write("Sample Name\tMarker\tAllele 1\tHeight 1\t\nS\tTPOX\t8\t100\textra\n")
        with self.assertRaisesRegex(GeneMapperParserError, "Unnamed trailing column contains data"):
            load_project(path)

    def test_rejects_unnamed_interior_column(self):
        path = self._write("Sample Name\tMarker\t\tAllele 1\tHeight 1\nS\tTPOX\t\t8\t100\n")
        with self.assertRaisesRegex(GeneMapperParserError, "Blank column names"):
            load_project(path)

    def test_preserves_sparse_indexes_and_optional_peak_families(self):
        path = self._write(
            "Sample Name\tMarker\tAllele 1\tAllele 3\tHeight 1\tHeight 3\t"
            "Size 1\tSize 3\tArea 1\tArea 3\tMutation 3\tComment 3\n"
            "S\tTPOX\t8\t10\t100\t80\t347.2\t355.2\t4000\t3200\tM\tcheck\n"
        )
        calls = load_project(path).sample("S").markers["TPOX"].alleles
        self.assertEqual(tuple(call.allele_index for call in calls), (1, 3))
        self.assertEqual(str(calls[0].size_bp), "347.2")
        self.assertEqual(calls[1].area, 3200)
        self.assertEqual(calls[1].mutation, "M")
        self.assertEqual(calls[1].comment, "check")

    def test_allele_display_overflow_produces_explicit_warning(self):
        path = self._write(
            "Sample Name\tMarker\tAllele Display Overflow\tAllele 1\tHeight 1\nS\tTPOX\t1\t8\t100\n"
        )
        project = load_project(path)
        self.assertIn("allele-display overflow", project.warnings[0])

    def test_rejects_nonempty_extra_field(self):
        path = self._write(
            "Sample Name\tMarker\tDye\tAllele 1\tHeight 1\nS\tTPOX\tFAM\t8\t100\textra\n"
        )
        with self.assertRaises(GeneMapperParserError):
            load_project(path)

    def test_ignores_blank_rows(self):
        path = self._write(
            "Sample Name\tMarker\tDye\tAllele 1\tHeight 1\n\nS\tTPOX\tFAM\t8\t100\n\n"
        )
        self.assertEqual(load_project(path).sample_ids, ("S",))

    def test_rejects_empty_file(self):
        path = self._write("")
        with self.assertRaises(GeneMapperParserError):
            load_project(path)

    def test_custom_sample_id_column(self):
        path = self._write("Sample ID\tMarker\tDye\tAllele 1\tHeight 1\nID-1\tTPOX\tFAM\t8\t100\n")
        project = load_project(path, sample_id_column="Sample ID")
        self.assertEqual(project.sample_ids, ("ID-1",))
