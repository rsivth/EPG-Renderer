# Coordinate model

EPG-Renderer draws schematic called peaks. A peak uses its measured fragment size when the source export provides `Size n`; otherwise it uses a kit-specific nominal display coordinate, a bounded repeat-based estimate or a verified exact bin centre. Nominal and estimated coordinates are not measured fragment sizes and must not be interpreted as an official GeneMapper bin set.

Each marker uses exactly one placement method:

- `explicit`: every ladder allele has an explicit coordinate.
- `range_centered_repeat`: numeric alleles are placed by repeat spacing within a documented nominal range.
- `anchored_repeat`: numeric alleles are placed relative to one documented allele/coordinate anchor.

Fields belonging to other placement methods are rejected. `exact_bin_centres=true` is permitted only when every marker uses complete explicit coordinates.

Alleles are canonicalized without collapsing biologically distinct microvariants. For example, `4.2` remains distinct from `42`. Unknown alleles, unknown markers and dye conflicts either raise a positioning error or become recorded issues when `position_sample` is called with `strict=False`. A missing source dye remains neutral, while a supplied dye that the selected kit cannot recognize is reported separately as `unknown_dye` in that mode. The rendering workflows (`render_file`, `render_file_report`, `render_batch`, `render_svg` for a `SampleCall`, the CLI and the GUI) check marker names and dyes against the kit before positioning and therefore always reject unknown markers and dye conflicts; there, permissive positioning only relaxes allele-level problems such as unknown alleles, missing heights or measured sizes outside the marker range.

In a manual profile, an off-ladder call entered as `OL@<allele>` is drawn at the repeat-based estimate of its helper allele and recorded as `estimated`, with the helper allele in `data-position-allele`. The helper allele must lie outside the ladder bins and its estimate inside the marker range; `position_sample` rejects helper alleles in GeneMapper samples.

Each positioned peak records one provenance value: `measured`, `nominal`, `estimated`, `exact_bin_centre` or `unpositioned`. Rendered peaks expose a neutral `data-coordinate-bp` value, a `data-coordinate-source` discriminator and a matching source-specific attribute. The document metadata records source counts and reports `mixed` when multiple coordinate sources occur. The SVG also retains the kit coordinate-model identifier, coordinate kind and exact-bin-centre flag because marker ranges and fallback positions still depend on that model.
