"""Run the static quality gates used for EPG-Renderer releases."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

_REQUIRED_MODULES = ("build", "coverage", "ruff", "mypy")


def _run(root: Path, *arguments: str) -> bool:
    result = subprocess.run(
        [sys.executable, *arguments],
        cwd=root,
        check=False,
    )
    return result.returncode == 0


def main() -> int:
    """Run every configured static quality check and report their status."""

    root = Path(__file__).resolve().parents[1]
    missing = [name for name in _REQUIRED_MODULES if importlib.util.find_spec(name) is None]
    if missing:
        print(
            "Missing development tools: "
            + ", ".join(missing)
            + '. Install them with: python -m pip install -e ".[dev]"',
            file=sys.stderr,
        )
        return 2

    lint_targets = ("src", "tests", "examples", "tools", "packaging", "launch_gui.py")
    compile_targets = ("src", "tests", "examples", "tools", "packaging", "launch_gui.py")
    checks = (
        ("Ruff lint", ("-m", "ruff", "check", *lint_targets)),
        ("Ruff format", ("-m", "ruff", "format", "--check", *lint_targets)),
        ("MyPy strict", ("-m", "mypy")),
        ("Compileall", ("-m", "compileall", "-q", *compile_targets)),
    )
    succeeded = True
    for label, arguments in checks:
        ok = _run(root, *arguments)
        print(f"{label}: {'passed' if ok else 'failed'}")
        succeeded = succeeded and ok
    print(f"All quality checks passed: {'yes' if succeeded else 'no'}")
    return 0 if succeeded else 1


if __name__ == "__main__":
    raise SystemExit(main())
