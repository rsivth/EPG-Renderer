# GeneMapper input requirements

EPG-Renderer reads delimited GeneMapper genotype-table exports. It does not read raw
`.fsa` files, electrophoresis project files, analysis methods, panels, bin sets, or
allelic ladders directly.

## Export the genotype table

GeneMapper exports the columns currently displayed by the selected table setting.
There is therefore no single universal CSV schema. Before exporting:

1. Select a genotype-oriented table containing one row per sample and marker.
2. Include enough indexed allele columns to retain every called peak that should be
   visualized, including stutter or additional mixture peaks when relevant.
3. Include the corresponding indexed height columns.
4. Include fragment-size columns when measured x-positions should be preserved.
5. Retain sample identity fields that distinguish repeated names or injections.

The parser warns when the highest exported allele column is populated because the
display setting may have truncated additional peaks. A warning is not proof of
truncation; it identifies a boundary that requires review against the original
analysis.

## Required and optional columns

The default file workflow expects:

| Column family | Requirement | Meaning |
|---|---|---|
| `Sample Name` | Required by default | Display name and default sample selector |
| `Marker` | Required | Locus or control name |
| `Allele 1`, `Allele 2`, … | At least one indexed column required | Called peak labels |
| `Height 1`, `Height 2`, … | Matching indexed family required | Imported RFU values |
| `Dye` | Optional | Channel evidence used for kit matching and validation |
| `Size 1`, `Size 2`, … | Optional | Measured fragment sizes for x-positioning |
| `Area n`, `Mutation n`, `Comment n` | Optional | Preserved indexed source metadata |
| `Sample File`, `Sample ID`, `Run Name` | Optional but recommended | Injection identity and duplicate-name separation |
| `Allele Display Overflow` or `ADO` | Optional | Explicit export-width warning evidence |

Header comparison ignores case and surrounding whitespace. Indexed peak fields are
paired by their numeric suffix; column position alone does not define a pair.

The Python API and CLI can select a non-default sample identifier column explicitly.
The GUI uses the standard `Sample Name` contract.

## Supported file encoding and delimiters

Automatic decoding tries, in order:

1. UTF-8 with optional byte-order mark
2. UTF-8
3. Windows-1252
4. Latin-1

Supported delimiters are tab, semicolon, and comma. Automatic detection scores the
header for GeneMapper semantics instead of choosing solely by punctuation frequency.

Quoted fields and physical line numbers are preserved during validation. Invalid CSV
quoting, duplicate headers, non-empty fields beyond the header, and unsupported
delimiters fail explicitly.

## Sample and marker identity

Repeated display names are not automatically merged. When available, `Sample File`,
`Sample ID`, and `Run Name` provide source-injection identity. The project assigns
readable unique identifiers while retaining the original fields separately.

Within one source injection, a marker may occur only once after normalized name
comparison. Duplicate marker rows are rejected instead of being silently combined.

## Numeric validity

- Imported RFU heights must be whole numbers from 0 through 32,767.
- A populated allele without its required height is rejected.
- Optional size and area values must be valid finite numeric values when present.
- A measured size outside the selected kit's marker range is a positioning error. With
  permissive positioning the peak is omitted and reported as
  `measured_size_outside_range`.
- The 32,767-RFU ceiling is a structural supported-domain limit, not a universal
  analytical threshold. Data from a 3500/3500xL may already be off-scale above
  32,000 RFU and requires upstream review.

See [sources and provenance](SOURCES.md#rfu-validity-boundary) for the manufacturer
basis of the boundary.

## Kit resolution

Kit matching considers marker names, order, and available dye evidence. Missing dye
information is neutral; a supplied incompatible dye is evidence against a profile.
Automatic rendering proceeds only when one bundled GeneMapper-compatible kit can be
resolved unambiguously. Otherwise, select the correct compatible kit explicitly.

PowerPlex 35GY is bundled for declarative kit and manual-profile use but is not
declared GeneMapper-export compatible.

## Fail-closed behavior

EPG-Renderer rejects malformed or ambiguous source boundaries rather than discarding
rows or inventing values. Do not "repair" a rejected export by deleting unfamiliar
columns until the reported error has been compared with the original GeneMapper table
and export setting.

Parser warnings remain attached to the loaded project and should be surfaced by
applications using the Python API.

Continue with the [GUI manual](GETTING_STARTED.md), [CLI guide](CLI.md),
[coordinate model](COORDINATE_MODEL.md), or return to the
[documentation home](index.md).
