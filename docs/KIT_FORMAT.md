# Declarative kit format

Bundled profiles are JSON files in `src/epg_renderer/data/kits/` and are validated against `src/epg_renderer/data/kit_definition_schema.json`. The only supported schema version is `1.1`.

## Top-level structure

A profile contains `schema_version`, `kit`, `coordinate_model`, `sources`, `markers` and `metadata`. Unknown fields are rejected.

The `kit` object defines the canonical name, display name, manufacturer, definition version, aliases, kit type, export compatibility, notes, linkage groups and ordered dye channels. Normalized names and aliases must remain non-empty and unambiguous.

Each marker defines its canonical name, aliases, dye, order within the dye, ladder alleles, marker type, optional copy/linkage group and one coordinate object. Control status is encoded consistently with `marker_type`. Linkage-group membership must agree in both the marker and kit-level declarations.

## Coordinate methods

`explicit` accepts only `explicit_positions` plus common range/source fields. `range_centered_repeat` accepts repeat length plus its range. `anchored_repeat` additionally requires `anchor_allele` and `anchor_bp`. Method-specific fields may not be mixed.

Explicit position keys must exactly cover the ladder alleles after canonicalization. Decimal microvariants remain distinct. A profile may claim exact bin centres only when every marker is explicitly and completely positioned.

## Provenance

Every source entry states a title and the data transcribed from that source. `review_status` is one of `manual_transcription`, `verified_analysis_file` or `user_supplied`. Nominal coordinates must be described as nominal in `source_note`.

## Adding a profile

1. Create one uniquely named JSON file in `data/kits/`.
2. Transcribe marker order, channels, aliases and ladder alleles from authoritative sources.
3. Use nominal coordinates unless exact bins were independently verified.
4. Add profile-specific validation, detection, positioning and rendering tests. When a complete source export is available, retain it unchanged as a hashed end-to-end fixture.
5. Verify that automatic matching distinguishes the profile from kits with overlapping marker sets; absent dye evidence must not be treated as agreement strong enough for an exact match.
6. Run `python -m tools.run_release_checks`.
