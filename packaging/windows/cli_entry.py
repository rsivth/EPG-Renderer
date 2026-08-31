"""PyInstaller entry point for the standalone EPG-Renderer command line."""

from epg_renderer.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
