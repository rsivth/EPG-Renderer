"""Exercise the extracted source archive without rerunning the full test suite."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from epg_renderer import __version__, list_kits, render_file  # noqa: E402


def main() -> int:
    """Verify import, bundled kits and one deterministic SVG render."""

    fixture = ROOT / "tests" / "fixtures" / "globalfiler_minimal.tsv"
    with tempfile.TemporaryDirectory(prefix="epg-renderer-source-smoke-") as directory:
        output = Path(directory) / "smoke.svg"
        render_file(fixture, output, kit_name="GlobalFiler")
        svg = output.read_text(encoding="utf-8")
    assert len(list_kits()) == 14
    assert f'data-epg-renderer-version="{__version__}"' in svg
    assert 'data-kit="GlobalFiler"' in svg
    print("Extracted source smoke test: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
