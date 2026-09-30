"""Exercise packaged EPG-Renderer executables outside their build tree."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

EXPECTED_KITS = (
    "GlobalFiler",
    "Identifiler",
    "Investigator Argus X-12",
    "Investigator ESSplex SE QS",
    "NGM Detect",
    "NGM SElect",
    "NGM",
    "PowerPlex 35GY",
    "PowerPlex ESI 17 Fast",
    "PowerPlex ESX 17 Fast",
    "PowerPlex Fusion",
    "PowerPlex Y23",
    "Yfiler Direct",
    "Yfiler Plus",
)
_REMOVED_ENVIRONMENT_KEYS = {
    "CAIROCFFI_DLL_DIRECTORIES",
    "CONDA_PREFIX",
    "DYLD_LIBRARY_PATH",
    "LD_LIBRARY_PATH",
    "TCL_LIBRARY",
    "TK_LIBRARY",
    "VIRTUAL_ENV",
}
_EXPECTED_VERSION = re.compile(r"\d+\.\d+\.\d+(?:rc\d+|\.dev\d+)?")


class BinarySmokeError(RuntimeError):
    """Raised when a packaged executable fails its release smoke test."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli", required=True, type=Path, help="Packaged CLI executable")
    parser.add_argument("--gui", required=True, type=Path, help="GUI executable inside its bundle")
    parser.add_argument("--fixture", required=True, type=Path, help="GeneMapper smoke fixture")
    parser.add_argument(
        "--expected-version",
        required=True,
        help="Expected project version: X.Y.Z, X.Y.ZrcN or X.Y.Z.devN",
    )
    return parser


def _isolated_environment(runtime_temp: Path) -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("PYTHON") and key.upper() not in _REMOVED_ENVIRONMENT_KEYS
    }
    environment["PATH"] = ""
    environment["TEMP"] = str(runtime_temp)
    environment["TMP"] = str(runtime_temp)
    return environment


def _copy_artifacts(cli: Path, gui: Path, destination: Path) -> tuple[Path, Path]:
    if not cli.is_file():
        raise BinarySmokeError(f"CLI executable is missing: {cli}")
    if not gui.is_file():
        raise BinarySmokeError(f"GUI executable is missing: {gui}")

    cli_directory = destination / "cli"
    cli_directory.mkdir(parents=True)
    isolated_cli = Path(shutil.copy2(cli, cli_directory / cli.name))

    gui_directory = destination / "gui" / gui.parent.name
    shutil.copytree(gui.parent, gui_directory)
    isolated_gui = gui_directory / gui.name
    if not isolated_gui.is_file():
        raise BinarySmokeError("The copied GUI bundle does not contain its executable.")
    return isolated_cli, isolated_gui


def _diagnostic(result: subprocess.CompletedProcess[str]) -> str:
    text = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
    return text[-4000:] if text else "no process output"


def _run(
    executable: Path,
    *arguments: str,
    cwd: Path,
    environment: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            [str(executable.resolve()), *arguments],
            cwd=cwd,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=90,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BinarySmokeError(f"Could not run {executable.name}: {exc}") from exc
    if result.returncode != 0:
        raise BinarySmokeError(
            f"{executable.name} returned {result.returncode}: {_diagnostic(result)}"
        )
    return result


def _verify_version(output: str, expected_version: str) -> None:
    expected = f"epg-render {expected_version}"
    if output.strip() != expected:
        raise BinarySmokeError(
            f"Unexpected version output: {output.strip()!r}; expected {expected!r}"
        )


def _verify_help(output: str) -> None:
    missing = [
        phrase
        for phrase in ("usage: epg-render", "--all-samples", "--list-kits", ".svg", ".jpg")
        if phrase not in output
    ]
    if missing:
        raise BinarySmokeError(f"CLI help is incomplete; missing {missing!r}.")


def _verify_kits(output: str) -> None:
    actual = tuple(line.strip() for line in output.splitlines() if line.strip())
    if actual != EXPECTED_KITS:
        raise BinarySmokeError(f"Bundled kit inventory differs: {actual!r}")


def _verify_svg(path: Path, expected_version: str) -> None:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise BinarySmokeError(f"SVG output is missing or invalid: {exc}") from exc
    if root.attrib.get("data-epg-renderer-version") != expected_version:
        raise BinarySmokeError("SVG output contains the wrong EPG-Renderer version.")
    if root.attrib.get("data-kit") != "GlobalFiler":
        raise BinarySmokeError("SVG output contains the wrong kit metadata.")


def _verify_jpeg(path: Path) -> None:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise BinarySmokeError(f"JPEG output is missing: {exc}") from exc
    if (
        len(payload) < 1024
        or not payload.startswith(b"\xff\xd8\xff")
        or not payload.endswith(b"\xff\xd9")
    ):
        raise BinarySmokeError("JPEG output does not have a complete JPEG file signature.")


def _verify_batch(directory: Path, expected_version: str) -> None:
    manifest_path = directory / "epg_batch_manifest.json"
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BinarySmokeError(f"Batch manifest is missing or invalid: {exc}") from exc
    if payload.get("epg_renderer_version") != expected_version:
        raise BinarySmokeError("Batch manifest contains the wrong EPG-Renderer version.")
    if payload.get("succeeded") != 1 or payload.get("failed") != 0:
        raise BinarySmokeError("Batch render did not report one successful sample.")
    items = payload.get("items")
    if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
        raise BinarySmokeError("Batch manifest item inventory is invalid.")
    output_name = items[0].get("output_file")
    if not isinstance(output_name, str) or Path(output_name).name != output_name:
        raise BinarySmokeError("Batch manifest output path is invalid.")
    _verify_svg(directory / output_name, expected_version)


def _check_expected_version(expected_version: str) -> None:
    """Accept the same version formats as the Windows build (``spec_common.py``)."""

    if _EXPECTED_VERSION.fullmatch(expected_version) is None:
        raise BinarySmokeError(
            "Expected version must have the form X.Y.Z, X.Y.ZrcN or X.Y.Z.devN: "
            f"{expected_version!r}"
        )


def _run_checks(
    cli: Path,
    gui: Path,
    fixture: Path,
    expected_version: str,
    workspace: Path,
) -> None:
    if not fixture.is_file():
        raise BinarySmokeError(f"GeneMapper fixture is missing: {fixture}")
    _check_expected_version(expected_version)

    artifacts = workspace / "artifacts"
    isolated_cli, isolated_gui = _copy_artifacts(cli.resolve(), gui.resolve(), artifacts)
    inputs = workspace / "inputs"
    inputs.mkdir()
    isolated_fixture = Path(shutil.copy2(fixture, inputs / "smoke.tsv"))
    outputs = workspace / "outputs"
    outputs.mkdir()
    runtime_temp = workspace / "runtime-temp"
    runtime_temp.mkdir()
    environment = _isolated_environment(runtime_temp)

    result = _run(isolated_cli, "--version", cwd=outputs, environment=environment)
    _verify_version(result.stdout, expected_version)
    print("Version: passed")

    result = _run(isolated_cli, "--help", cwd=outputs, environment=environment)
    _verify_help(result.stdout)
    print("Help: passed")

    result = _run(isolated_cli, "--list-kits", cwd=outputs, environment=environment)
    _verify_kits(result.stdout)
    print("Kit resources: passed")

    svg = outputs / "single.svg"
    _run(
        isolated_cli,
        str(isolated_fixture),
        str(svg),
        "--kit",
        "GlobalFiler",
        cwd=outputs,
        environment=environment,
    )
    _verify_svg(svg, expected_version)
    print("SVG rendering: passed")

    jpeg = outputs / "single.jpg"
    _run(
        isolated_cli,
        str(isolated_fixture),
        str(jpeg),
        "--kit",
        "GlobalFiler",
        "--raster-scale",
        "0.25",
        cwd=outputs,
        environment=environment,
    )
    _verify_jpeg(jpeg)
    print("JPEG rendering: passed")

    batch = outputs / "batch"
    _run(
        isolated_cli,
        str(isolated_fixture),
        str(batch),
        "--kit",
        "GlobalFiler",
        "--all-samples",
        cwd=outputs,
        environment=environment,
    )
    _verify_batch(batch, expected_version)
    print("Batch rendering: passed")

    _run(isolated_gui, "--check", cwd=outputs, environment=environment)
    print("GUI startup dependencies: passed")
    print("Isolated runtime: passed")


def main(argv: list[str] | None = None) -> int:
    """Run every packaged-binary smoke test and report one final result."""

    args = _parser().parse_args(argv)
    try:
        with tempfile.TemporaryDirectory(prefix="epg-renderer-binary-smoke-") as directory:
            _run_checks(
                args.cli,
                args.gui,
                args.fixture,
                args.expected_version,
                Path(directory),
            )
    except BinarySmokeError as exc:
        print(f"Binary smoke tests failed: {exc}", file=sys.stderr)
        print("All binary smoke tests passed: no")
        return 1
    print("All binary smoke tests passed: yes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
