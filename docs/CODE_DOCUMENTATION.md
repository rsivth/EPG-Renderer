# Source-code documentation policy

EPG-Renderer documents contracts and scientific assumptions at the point where they are enforced. Documentation is part of the release quality gate rather than an optional editorial step.

## Public interfaces

Every public module, class, function and method has a docstring. Public entry points describe the operation performed, the relevant input and output contract, and any scientific limitation that materially affects interpretation. Detailed parameter lists remain in the type annotations and API manual when repeating them in a docstring would add noise.

## Scientific terminology

The renderer distinguishes measured values from derived display values:

- RFU heights are copied from the genotype-table export.
- RFU height validation uses the shared manufacturer-backed 32,767-RFU structural ceiling in `epg_renderer.rfu`; instrument-specific off-scale review remains an upstream quality-control responsibility.
- Exported fragment sizes, nominal kit coordinates, repeat-based estimates and verified exact bin centres remain distinguished by per-peak provenance.
- Nominal and estimated coordinates are schematic display positions rather than measured fragment sizes.
- A rendered peak is not reconstructed raw electrophoretic signal.

These distinctions must remain explicit in coordinate, positioning and rendering documentation.

## Comments

Comments are reserved for non-obvious rationale, invariants and external constraints. They must not restate the next line of code, preserve release history, mention superseded tests, or justify compatibility code that no longer exists. Version history belongs in `CHANGELOG.md`; architecture decisions belong in the technical documentation.

## Enforcement

Ruff's pydocstyle rules enforce module and public-object documentation. Regression tests reject stale version-, legacy- and test-oriented commentary in production modules. The complete gate is run with:

```bash
python -m tools.run_quality_checks
```
