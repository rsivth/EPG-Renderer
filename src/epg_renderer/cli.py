"""Command-line interface for EPG-Renderer."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from .batch import render_genemapper_batch
from .kit_registry import available_genemapper_kit_names, available_kit_names
from .render_options import (
    OutputFormat,
    RasterRenderOptions,
    SvgRenderOptions,
    UnpositionedPolicy,
    YellowChannelMode,
)
from .version import __version__
from .workflow import render_genemapper_epg


class _ListKitsAction(argparse.Action):
    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: object,
        option_string: str | None = None,
    ) -> None:
        del namespace, values, option_string
        print("\n".join(available_kit_names()))
        parser.exit()


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line argument parser without reading process state."""
    parser = argparse.ArgumentParser(
        prog="epg-render",
        description=(
            "Create a schematic kit-aware electropherogram from a GeneMapper "
            "genotype CSV/TSV export. The output format follows the file suffix."
        ),
    )
    parser.add_argument("input", type=Path, help="GeneMapper CSV/TSV input file")
    parser.add_argument(
        "output",
        type=Path,
        help="Output .svg, .png, .jpg or .jpeg file; with --all-samples, an output directory",
    )
    parser.add_argument("--sample-id", help="Sample ID when the export contains several samples")
    parser.add_argument(
        "--all-samples",
        action="store_true",
        help="Render every sample into the output directory",
    )
    parser.add_argument(
        "--format",
        choices=["svg", "png", "jpg", "jpeg"],
        default="svg",
        help="Batch output format used with --all-samples (default: svg)",
    )
    parser.add_argument(
        "--kit",
        dest="kit_name",
        help=(
            "Explicit kit name or alias; GeneMapper-compatible bundled kits: "
            + ", ".join(available_genemapper_kit_names())
        ),
    )
    parser.add_argument(
        "--sample-id-column",
        help="Alternative column name containing the sample identifier",
    )
    parser.add_argument(
        "--title",
        help="Optional title used in the output image",
    )
    parser.add_argument(
        "--raster-scale",
        type=float,
        default=2.0,
        help="PNG/JPEG scale factor (default: 2.0)",
    )
    parser.add_argument(
        "--jpeg-quality",
        type=int,
        default=95,
        help="JPEG quality from 1 to 100 (default: 95)",
    )
    parser.add_argument(
        "--yellow-channel",
        choices=[mode.value for mode in YellowChannelMode],
        default=YellowChannelMode.YELLOW.value,
        help="Display channels defined as yellow in yellow or black (default: yellow)",
    )
    parser.add_argument(
        "--permissive-positioning",
        action="store_true",
        help="Allow unknown alleles and omit unpositioned peaks instead of failing",
    )
    parser.add_argument(
        "--list-kits",
        action=_ListKitsAction,
        nargs=0,
        help="List all bundled kit resources and exit",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface and return a process exit status."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return _run_command(args)
    except (OSError, ValueError) as exc:
        print(f"epg-render: error: {exc}", file=__import__("sys").stderr)
        return 2


def _run_command(args: argparse.Namespace) -> int:
    """Execute one validated command-line request."""
    svg_options = SvgRenderOptions(
        title=args.title,
        yellow_channel_mode=args.yellow_channel,
        unpositioned_policy=(
            UnpositionedPolicy.OMIT if args.permissive_positioning else UnpositionedPolicy.ERROR
        ),
    )
    raster_options = RasterRenderOptions(
        scale=args.raster_scale,
        jpeg_quality=args.jpeg_quality,
    )
    if args.all_samples:
        if args.sample_id:
            raise ValueError("--sample-id cannot be combined with --all-samples")
        fmt = "jpeg" if args.format in {"jpg", "jpeg"} else args.format
        result = render_genemapper_batch(
            args.input,
            args.output,
            output_format=OutputFormat(fmt),
            kit_name=args.kit_name,
            options=svg_options,
            raster_options=raster_options,
            strict_positioning=not args.permissive_positioning,
            sample_id_column=args.sample_id_column,
        )
        print(f"Output directory: {result.output_dir.resolve()}")
        print(f"Rendered: {result.succeeded}; failed: {result.failed}")
        print(f"Manifest: {result.manifest_path.resolve()}")
        return 0 if result.failed == 0 else 2
    render_genemapper_epg(
        args.input,
        args.output,
        sample_id=args.sample_id,
        kit_name=args.kit_name,
        options=svg_options,
        raster_options=raster_options,
        strict_positioning=not args.permissive_positioning,
        sample_id_column=args.sample_id_column,
    )
    print(args.output.resolve())
    return 0
