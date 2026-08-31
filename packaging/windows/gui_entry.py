"""PyInstaller entry point for the standalone EPG-Renderer GUI."""

from __future__ import annotations

import sys


def _main() -> int:
    checking = sys.argv[1:] == ["--check"]
    try:
        from epg_renderer.gui import main

        return main()
    except Exception as exc:
        if not checking:
            raise
        if sys.stderr is not None:
            print(f"EPG-Renderer GUI check failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(_main())
