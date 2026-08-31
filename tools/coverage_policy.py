"""Line and branch coverage thresholds for EPG-Renderer release checks."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CoverageTarget:
    """Minimum line and branch coverage required for one source module."""

    module: str
    minimum_line_percent: float
    minimum_branch_percent: float
    rationale: str


COVERAGE_TARGETS = (
    CoverageTarget("api.py", 95.0, 90.0, "The canonical public API is a release boundary."),
    CoverageTarget("batch.py", 95.0, 90.0, "Batch isolation and manifests are release-critical."),
    CoverageTarget("domain.py", 95.0, 90.0, "Typed metadata must reject invalid public states."),
    CoverageTarget("kit_registry.py", 95.0, 90.0, "Bundled kit discovery is a trust boundary."),
    CoverageTarget("kit_schema.py", 90.0, 80.0, "Kit validation has extensive negative paths."),
    CoverageTarget("kit_workflow.py", 98.0, 95.0, "Kit resolution is a core decision."),
    CoverageTarget("kits.py", 95.0, 90.0, "Validated kit types are central domain objects."),
    CoverageTarget("models.py", 95.0, 90.0, "Immutable call models enforce invariants."),
    CoverageTarget(
        "parser.py", 95.0, 90.0, "Malformed GeneMapper input must fail deterministically."
    ),
    CoverageTarget("positions.py", 90.0, 85.0, "Allele positioning is a core transformation."),
    CoverageTarget("render_io.py", 95.0, 90.0, "Atomic output and raster boundaries are critical."),
    CoverageTarget("render_document.py", 95.0, 90.0, "Document assembly is deterministic."),
    CoverageTarget(
        "render_layout.py", 90.0, 80.0, "Layout calculations must remain deterministic."
    ),
    CoverageTarget("render_options.py", 95.0, 90.0, "Public rendering options require validation."),
    CoverageTarget("render_svg.py", 85.0, 70.0, "The SVG core also has golden-output tests."),
    CoverageTarget("gui_workflow.py", 75.0, 50.0, "Headless GUI decisions are tested separately."),
    CoverageTarget("workflow.py", 95.0, 90.0, "Single-sample orchestration is public."),
    CoverageTarget("cli.py", 80.0, 70.0, "The command-line boundary must handle user errors."),
)

MINIMUM_PACKAGE_LINE_COVERAGE = 85.0
MINIMUM_PACKAGE_BRANCH_COVERAGE = 78.0


__all__ = [
    "COVERAGE_TARGETS",
    "MINIMUM_PACKAGE_BRANCH_COVERAGE",
    "MINIMUM_PACKAGE_LINE_COVERAGE",
    "CoverageTarget",
]
