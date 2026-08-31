"""One-off generator for the synthetic GeneMapper export fixtures.

Produces tests/fixtures/genemapper_exports/essplex_se_qs_mixed_export.txt and
ngm_select_mixed_export.txt as fully invented data (no real samples, run names,
or laboratory identifiers), while reproducing the structural edge cases the
regression tests in tests/test_genemapper_exports.py rely on: an unnamed
trailing export column, a marker call that fills the highest displayed allele
column, and duplicate display names that must be kept as separate source
injections.

Not part of the installed package. Re-run this after touching the bundled
Investigator ESSplex SE QS or NGM SElect kit definitions to regenerate fixtures
that stay consistent with them; otherwise there is no need to run it again.
Re-running it reproduces the exact same two files byte-for-byte (the random
generator is seeded), so the committed fixtures and this script never drift
apart silently.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KITS = ROOT / "src" / "epg_renderer" / "data" / "kits"
OUT = ROOT / "tests" / "fixtures" / "genemapper_exports"

MAX_ALLELE_COLUMNS = 20


def load_markers(kit_file: str) -> list[tuple[str, list[str]]]:
    data = json.loads((KITS / kit_file).read_text(encoding="utf-8"))
    markers = sorted(data["markers"], key=lambda m: (_dye_order(data, m["dye"]), m["order_in_dye"]))
    return [(m["name"], m["ladder_alleles"]) for m in markers]


def _dye_order(data: dict, dye_code: str) -> int:
    for channel in data["kit"]["channels"]:
        if channel["code"] == dye_code:
            return channel["order"]
    raise KeyError(dye_code)


def build_row(
    sample_file: str,
    sample_name: str,
    sample_id: str,
    run_name: str,
    marker: str,
    alleles: list[str],
    heights: list[int],
) -> list[str]:
    row = [sample_file, sample_name, sample_id, run_name, marker]
    allele_cells = [""] * MAX_ALLELE_COLUMNS
    height_cells = [""] * MAX_ALLELE_COLUMNS
    for index, (allele, height) in enumerate(zip(alleles, heights, strict=True)):
        allele_cells[index] = allele
        height_cells[index] = str(height)
    row.extend(allele_cells)
    row.extend(height_cells)
    row.append("")  # unnamed trailing export column, present but always empty
    return row


def write_export(path: Path, rows: list[list[str]]) -> None:
    header = (
        ["Sample File", "Sample Name", "Sample ID", "Run Name", "Marker"]
        + [f"Allele {i}" for i in range(1, MAX_ALLELE_COLUMNS + 1)]
        + [f"Height {i}" for i in range(1, MAX_ALLELE_COLUMNS + 1)]
        + [""]
    )
    lines = ["\t".join(header)]
    lines.extend("\t".join(row) for row in rows)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def fake_uuid(rng: random.Random) -> str:
    return "-".join(
        "".join(rng.choice("0123456789abcdef") for _ in range(n)) for n in (8, 4, 4, 4, 12)
    )


def _sort_key(allele: str) -> tuple[int, float | str]:
    try:
        return (0, float(allele))
    except ValueError:
        return (1, allele)


def pick_alleles(rng: random.Random, ladder: list[str], count: int) -> list[str]:
    count = min(count, len(ladder))
    return sorted(rng.sample(ladder, count), key=_sort_key)


def heights_for(rng: random.Random, count: int, low: int, high: int) -> list[int]:
    return [rng.randint(low, high) for _ in range(count)]


def build_essplex() -> None:
    rng = random.Random("essplex-synthetic-fixture")
    markers = load_markers("investigator_essplex_v1.json")
    marker_names = [name for name, _ in markers]
    assert marker_names[0] == "QS1" and marker_names[6] == "QS2"

    rows: list[list[str]] = []

    def sample(sample_file: str, sample_name: str, run_name: str, profile) -> None:
        sample_id = fake_uuid(rng)
        for marker, ladder in markers:
            alleles, heights = profile(marker, ladder)
            rows.append(
                build_row(sample_file, sample_name, sample_id, run_name, marker, alleles, heights)
            )

    def negative_control(marker: str, ladder: list[str]) -> tuple[list[str], list[int]]:
        if marker == "QS1":
            return ["Q"], [rng.randint(850, 1050)]
        if marker == "QS2":
            return ["S"], [rng.randint(1050, 1250)]
        return [], []

    def reference_control(marker: str, ladder: list[str]) -> tuple[list[str], list[int]]:
        if marker == "QS1":
            return ["Q"], [rng.randint(1100, 1400)]
        if marker == "QS2":
            return ["S"], [rng.randint(1300, 1600)]
        n = rng.choice([1, 2])
        alleles = pick_alleles(rng, ladder, n)
        return alleles, heights_for(rng, len(alleles), 8500, 11000)

    def kit_reference(marker: str, ladder: list[str]) -> tuple[list[str], list[int]]:
        # Broad marker/allele coverage for unambiguous kit identification,
        # capped at the displayed column width like a real truncated export.
        if marker in ("QS1", "QS2"):
            allele = "Q" if marker == "QS1" else "S"
            return [allele], [rng.randint(1400, 1700)]
        n = min(len(ladder), MAX_ALLELE_COLUMNS)
        alleles = sorted(ladder[:n], key=_sort_key)
        return alleles, heights_for(rng, n, 1900, 2450)

    def two_person_mix(marker: str, ladder: list[str]) -> tuple[list[str], list[int]]:
        if marker == "QS1":
            return ["Q"], [rng.randint(1200, 1500)]
        if marker == "QS2":
            return ["S"], [rng.randint(1400, 1700)]
        n = rng.choice([2, 3, 4])
        alleles = pick_alleles(rng, ladder, n)
        return alleles, heights_for(rng, len(alleles), 300, 2200)

    def three_person_mix(marker: str, ladder: list[str]) -> tuple[list[str], list[int]]:
        if marker == "QS1":
            return ["Q"], [rng.randint(1200, 1500)]
        if marker == "QS2":
            return ["S"], [rng.randint(1400, 1700)]
        n = rng.choice([3, 4, 5, 6])
        alleles = pick_alleles(rng, ladder, n)
        return alleles, heights_for(rng, len(alleles), 150, 1800)

    def dense_mixture(marker: str, ladder: list[str]) -> tuple[list[str], list[int]]:
        # Deliberately fills every displayed allele column on SE33 so the
        # "highest allele column populated" truncation warning still fires.
        if marker == "QS1":
            return ["Q"], [rng.randint(1200, 1500)]
        if marker == "QS2":
            return ["S"], [rng.randint(1400, 1700)]
        if marker == "SE33":
            n = min(len(ladder), MAX_ALLELE_COLUMNS)
            alleles = sorted(rng.sample(ladder, n), key=_sort_key)
            return alleles, heights_for(rng, n, 120, 1500)
        n = rng.choice([4, 5, 6])
        alleles = pick_alleles(rng, ladder, n)
        return alleles, heights_for(rng, len(alleles), 120, 1600)

    def single_source(marker: str, ladder: list[str]) -> tuple[list[str], list[int]]:
        if marker == "QS1":
            return ["Q"], [rng.randint(1200, 1500)]
        if marker == "QS2":
            return ["S"], [rng.randint(1400, 1700)]
        n = rng.choice([1, 2])
        alleles = pick_alleles(rng, ladder, n)
        return alleles, heights_for(rng, len(alleles), 900, 3200)

    sample("A05_NK_Synth_01.hid", "NK_Synth", "9004X_ESS_02032026_ab-Synth", negative_control)
    sample("B05_Ref_Synth_02.hid", "Ref_Synth", "9004X_ESS_02032026_ab-Synth", reference_control)
    sample("C05_Ess_Leiter_03.hid", "Ess_Leiter", "9004X_ESS_02032026_ab-Synth", kit_reference)
    sample("D05_Case_Synth_04.hid", "Case_Synth_04", "9004X_ESS_02032026_ab-Synth", two_person_mix)
    sample(
        "E05_Case_Synth_05.hid", "Case_Synth_05", "9004X_ESS_02032026_ab-Synth", three_person_mix
    )
    sample("F05_Case_Synth_06.hid", "Case_Synth_06", "9004X_ESS_02032026_ab-Synth", dense_mixture)
    sample("G05_Case_Synth_07.hid", "Case_Synth_07", "9004X_ESS_02032026_ab-Synth", single_source)

    write_export(OUT / "essplex_se_qs_mixed_export.txt", rows)


def build_ngm_select() -> None:
    rng = random.Random("ngm-select-synthetic-fixture")
    markers = load_markers("ngm_select_v1.json")

    rows: list[list[str]] = []

    def sample(sample_file: str, sample_name: str, sample_id: str, run_name: str, profile) -> None:
        for marker, ladder in markers:
            alleles, heights = profile(marker, ladder)
            rows.append(
                build_row(sample_file, sample_name, sample_id, run_name, marker, alleles, heights)
            )

    def ladder_profile(low: int, high: int):
        def profile(marker: str, ladder: list[str]) -> tuple[list[str], list[int]]:
            n = min(len(ladder), MAX_ALLELE_COLUMNS)
            alleles = sorted(ladder[:n], key=_sort_key)
            return alleles, heights_for(rng, n, low, high)

        return profile

    def case_profile(marker: str, ladder: list[str]) -> tuple[list[str], list[int]]:
        if marker == "Amelogenin":
            sex = rng.choice([["X", "X"], ["X", "Y"]])
            return sex, heights_for(rng, len(sex), 900, 2600)
        n = rng.choice([1, 1, 2, 2, 2, 3])
        alleles = pick_alleles(rng, ladder, n)
        return alleles, heights_for(rng, len(alleles), 150, 2600)

    def low_template_profile(marker: str, ladder: list[str]) -> tuple[list[str], list[int]]:
        if marker == "Amelogenin":
            sex = rng.choice([["X", "X"], ["X", "Y"]])
            return sex, heights_for(rng, len(sex), 120, 700)
        if rng.random() < 0.15:
            return [], []
        n = rng.choice([1, 1, 2])
        alleles = pick_alleles(rng, ladder, n)
        return alleles, heights_for(rng, len(alleles), 60, 500)

    # Two source injections sharing the display name "Allelleiter" but
    # distinct Sample File/Sample ID/Run Name -- must stay separate samples.
    sample(
        "A01_Ladder_01.hid",
        "Allelleiter",
        fake_uuid(rng),
        "5217A_NGMS_09032026_rw-Synth",
        ladder_profile(2000, 2550),
    )
    sample(
        "H01_Ladder_08.hid",
        "Allelleiter",
        fake_uuid(rng),
        "5217A_NGMS_09032026_rw-Synth",
        ladder_profile(1950, 2500),
    )
    sample(
        "A02_Ladder_02.hid",
        "Allelleiter-1",
        fake_uuid(rng),
        "5217A_NGMS_09032026_rw-Synth",
        ladder_profile(2050, 2600),
    )

    for index in range(4, 32):
        run_name = (
            "5217A_NGMS_09032026_rw-Synth" if index % 2 == 0 else "5217A_NGMS_09032026_rw-Synth2"
        )
        profile = low_template_profile if index % 5 == 0 else case_profile
        sample(
            f"{chr(ord('A') + (index // 8))}{index % 8 + 1:02d}_Case_Synth_{index:02d}.hid",
            f"Case_Synth_{index:02d}",
            fake_uuid(rng),
            run_name,
            profile,
        )

    write_export(OUT / "ngm_select_mixed_export.txt", rows)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    build_essplex()
    build_ngm_select()
    print("wrote", OUT / "essplex_se_qs_mixed_export.txt")
    print("wrote", OUT / "ngm_select_mixed_export.txt")
