"""The summary block that every check tool prints as the last part of its output.

One format for all tools, modelled on STRio's ``run_tests.py``: a framed block of
aligned rows that ends with ``Result: PASSED`` or ``Result: FAILED``. Details such as
failing tests follow below the block, tool output of a failing check above it.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

WIDTH = 50
RULE = "-" * WIDTH


def package_version(root: Path) -> str:
    """Return ``__version__`` from ``src/epg_renderer/version.py`` without importing it."""

    source = (root / "src" / "epg_renderer" / "version.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', source, re.MULTILINE)
    return match.group(1) if match else "?"


def row(label: str, value: object) -> str:
    """Return one aligned row; numbers are right-aligned, other values left-aligned."""

    if isinstance(value, int) and not isinstance(value, bool):
        return f"{label:<23}{value:>6}"
    return f"{label:<23}{value}"


def block(title: str, rows: Iterable[str], passed: bool) -> str:
    """Return the framed block; ``RULE`` in ``rows`` draws a separator."""

    lines = ["=" * WIDTH, title, RULE, *rows, RULE]
    lines += [f"Result: {'PASSED' if passed else 'FAILED'}", "=" * WIDTH]
    return "\n".join(lines)
