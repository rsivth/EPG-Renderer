# Coordinate model

EPG-Renderer draws schematic called peaks. A peak uses its measured fragment size when the source export provides `Size n`; otherwise it uses a kit-specific nominal display coordinate, a bounded repeat-based estimate or a verified exact bin centre. Nominal and estimated coordinates are not measured fragment sizes and must not be interpreted as an official GeneMapper bin set.

Each marker uses exactly one placement method:

- `explicit`: every ladder allele has an explicit coordinate.
- `range_centered_repeat`: numeric alleles are placed by repeat spacing within a documented nominal range.
- `anchored_repeat`: numeric alleles are placed relative to one documented allele/coordinate anchor.

Fields belonging to other placement methods are rejected. `exact_bin_centres=true` is permitted only when every marker uses complete explicit coordinates.

Alleles are canonicalized without collapsing biologically distinct microvariants. For example, `4.2` remains distinct from `42`. Unknown alleles, unknown markers and dye conflicts either raise a positioning error or become recorded issues in permissive mode. A missing source dye remains neutral, while a supplied dye that the selected kit cannot recognize is reported separately as `unknown_dye` in permissive mode.

Each positioned peak records one provenance value: `measured`, `nominal`, `estimated`, `exact_bin_centre` or `unpositioned`. Rendered peaks expose a neutral `data-coordinate-bp` value, a `data-coordinate-source` discriminator and a matching source-specific attribute. The document metadata records source counts and reports `mixed` when multiple coordinate sources occur. The SVG also retains the kit coordinate-model identifier, coordinate kind and exact-bin-centre flag because marker ranges and fallback positions still depend on that model.
