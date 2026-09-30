"""Structural guards for fail-fast pairing and single helper definitions.

Paired sequences must have equal length; a silent ``zip`` truncation would drop peaks
from an image without any error. Private helpers are defined once, so that two copies
cannot drift apart.
"""

from __future__ import annotations

import ast
import unittest
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

from epg_renderer import position_sample
from epg_renderer.kit_registry import get_kit_profile
from epg_renderer.models import AlleleCall, MarkerCall, SampleCall
from epg_renderer.render_layout import plan_channel_labels, resolve_x_domain
from epg_renderer.render_options import SvgRenderOptions, validate_svg_options
from epg_renderer.render_svg import _ChannelRenderContext, _render_channel

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "epg_renderer"
KIT = "GlobalFiler"
MARKER = "D3S1358"

# Same name, deliberately different semantics (reviewed 2026-09-30):
# domain._required_text raises TypeError for non-strings, positions._required_text
# converts with str(); models._optional_text and positions._optional_text differ alike.
ACCEPTED_DUPLICATE_HELPERS = frozenset({"_required_text", "_optional_text"})


def _modules() -> list[tuple[str, ast.Module]]:
    return [
        (path.name, ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        for path in sorted(PACKAGE.glob("*.py"))
    ]


class ZipStrictnessTests(unittest.TestCase):
    def test_every_multi_sequence_zip_is_strict(self) -> None:
        findings: list[str] = []
        for name, tree in _modules():
            for node in ast.walk(tree):
                if not (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "zip"
                    and len(node.args) > 1
                ):
                    continue
                strict = {
                    keyword.arg: keyword.value for keyword in node.keywords if keyword.arg
                }.get("strict")
                if not (isinstance(strict, ast.Constant) and strict.value is True):
                    findings.append(f"{name}:{node.lineno}")
        self.assertEqual(findings, [])

    def test_channel_rendering_rejects_a_label_plan_for_fewer_peaks(self) -> None:
        calls = (AlleleCall(1, "15", 1200), AlleleCall(2, "17", 900))
        sample = SampleCall("S1", {MARKER: MarkerCall(MARKER, None, calls)})
        peaks = list(position_sample(sample, kit_name=KIT).peaks)
        self.assertEqual(len(peaks), 2)
        profile = get_kit_profile(KIT)
        options = validate_svg_options(SvgRenderOptions())
        x_min, x_max = resolve_x_domain(profile.coordinate_model.markers, options)
        plot_left = float(options.left_margin)
        plot_right = float(options.width - options.right_margin)
        plan = plan_channel_labels(
            peaks[:1],
            options=options,
            x_min=x_min,
            x_max=x_max,
            plot_left=plot_left,
            plot_right=plot_right,
        )
        channel = next(item for item in profile.kit.channels if item.code == peaks[0].dye)
        context = _ChannelRenderContext(
            root=ET.Element("svg"),
            channel=channel,
            channel_y=options.header_height,
            plan=plan,
            options=options,
            plot_width=int(plot_right - plot_left),
            x_min=x_min,
            x_max=x_max,
            max_rfu=2000,
            peaks=peaks,
            marker_definitions=tuple(
                marker for marker in profile.coordinate_model.markers if marker.dye == channel.code
            ),
            marker_annotation_counts={},
            color="#000000",
        )
        with self.assertRaises(ValueError):
            _render_channel(context)


class SingleHelperDefinitionTests(unittest.TestCase):
    def test_private_module_helpers_are_defined_once(self) -> None:
        locations: dict[str, list[str]] = defaultdict(list)
        for name, tree in _modules():
            for node in tree.body:
                if isinstance(node, ast.FunctionDef) and node.name.startswith("_"):
                    locations[node.name].append(name)
        duplicates = {
            helper: modules
            for helper, modules in locations.items()
            if len(modules) > 1 and helper not in ACCEPTED_DUPLICATE_HELPERS
        }
        self.assertEqual(duplicates, {})


if __name__ == "__main__":
    unittest.main()
