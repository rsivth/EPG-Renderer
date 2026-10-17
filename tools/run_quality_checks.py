"""Run the static quality gates used for EPG-Renderer releases.

The output of a tool is shown only if its check fails, above the summary block, so the
block with ``Result: PASSED`` or ``Result: FAILED`` is always the end of the output.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

from tools.console_report import block, package_version, row

_REQUIRED_MODULES = ("build", "coverage", "ruff", "mypy")


def _run(root: Path, *arguments: str) -> tuple[bool, str]:
    result = subprocess.run(
        [sys.executable, *arguments],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0, (result.stdout + result.stderr).strip()


def format_report(version: str, statuses: list[tuple[str, str]], succeeded: bool) -> str:
    """Return the summary block of the quality checks."""

    rows = [row(label, status) for label, status in statuses]
    return block(f"EPG-Renderer {version} · quality checks", rows, succeeded)


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
        statuses = [(name, "NOT INSTALLED") for name in missing]
        print(format_report(package_version(root), statuses, succeeded=False))
        return 2

    lint_targets = ("src", "tests", "examples", "tools", "packaging", "launch_gui.py")
    compile_targets = ("src", "tests", "examples", "tools", "packaging", "launch_gui.py")
    checks = (
        ("Ruff lint", ("-m", "ruff", "check", *lint_targets)),
        ("Ruff format", ("-m", "ruff", "format", "--check", *lint_targets)),
        ("MyPy strict", ("-m", "mypy")),
        ("Compileall", ("-m", "compileall", "-q", *compile_targets)),
    )
    statuses: list[tuple[str, str]] = []
    for label, arguments in checks:
        ok, output = _run(root, *arguments)
        statuses.append((label, "passed" if ok else "FAILED"))
        if not ok:
            print(f"--- {label} ---\n{output}\n", flush=True)
    succeeded = all(status == "passed" for _, status in statuses)
    print(format_report(package_version(root), statuses, succeeded))
    return 0 if succeeded else 1


if __name__ == "__main__":
    raise SystemExit(main())
