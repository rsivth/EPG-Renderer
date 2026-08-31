"""Build and package the verified Windows x64 GUI and CLI deliverables."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

from tools.release_tools import (
    DEFAULT_SOURCE_DATE_EPOCH,
    ReleaseError,
    project_version,
    sha256_file,
)


@dataclass(frozen=True, slots=True)
class WindowsBinaryArtifacts:
    """Paths to the two packaged Windows deliverables."""

    version: str
    cli_executable: Path
    gui_archive: Path


def _run_pyinstaller(root: Path, spec: Path, dist: Path, work: Path, *, epoch: int) -> None:
    environment = {
        **os.environ,
        "PYTHONHASHSEED": "0",
        "SOURCE_DATE_EPOCH": str(epoch),
    }
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--clean",
            "--noconfirm",
            "--distpath",
            str(dist),
            "--workpath",
            str(work),
            str(spec),
        ],
        cwd=root,
        env=environment,
        check=False,
    )
    if result.returncode != 0:
        raise ReleaseError(f"PyInstaller failed for {spec.name} with status {result.returncode}.")


def _verify_dist_tree(dist: Path) -> tuple[Path, Path]:
    expected = {"EPG-Renderer-GUI", "epg-render.exe"}
    try:
        actual = {path.name for path in dist.iterdir()}
    except OSError as exc:
        raise ReleaseError(f"Could not inspect the Windows build output: {exc}") from exc
    if actual != expected:
        raise ReleaseError(f"Unexpected Windows build inventory: {sorted(actual)!r}")

    cli = dist / "epg-render.exe"
    gui = dist / "EPG-Renderer-GUI"
    gui_inventory = {path.name for path in gui.iterdir()} if gui.is_dir() else set()
    if not cli.is_file():
        raise ReleaseError("The stable CLI executable epg-render.exe is missing.")
    if gui_inventory != {"EPG-Renderer-GUI.exe", "_internal"}:
        raise ReleaseError(f"Unexpected GUI bundle inventory: {sorted(gui_inventory)!r}")
    if not (gui / "EPG-Renderer-GUI.exe").is_file() or not (gui / "_internal").is_dir():
        raise ReleaseError("The GUI onedir bundle is incomplete.")
    return cli, gui


def _zip_info(name: str, epoch: int) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=time.gmtime(max(epoch, 315532800))[:6])
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    info.flag_bits |= 0x800
    return info


def _write_gui_archive(gui: Path, license_path: Path, target: Path, *, epoch: int) -> None:
    members = [
        (f"{gui.name}/{path.relative_to(gui).as_posix()}", path)
        for path in gui.rglob("*")
        if path.is_file()
    ]
    members.append((f"{gui.name}/LICENSE", license_path))
    members.sort(key=lambda item: item[0].casefold())
    if len({name for name, _path in members}) != len(members):
        raise ReleaseError("The GUI archive would contain duplicate member names.")
    with zipfile.ZipFile(
        target,
        mode="x",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
        strict_timestamps=True,
    ) as archive:
        for name, source in members:
            with (
                source.open("rb") as input_file,
                archive.open(_zip_info(name, epoch), "w") as output,
            ):
                shutil.copyfileobj(input_file, output, length=1024 * 1024)


def _package_artifacts(
    root: Path,
    dist: Path,
    output_dir: Path,
    *,
    version: str,
    epoch: int,
) -> WindowsBinaryArtifacts:
    cli, gui = _verify_dist_tree(dist)
    license_path = root / "LICENSE"
    if not license_path.is_file():
        raise ReleaseError("LICENSE is missing from the source tree.")
    if output_dir.exists():
        if not output_dir.is_dir():
            raise ReleaseError(f"Windows artifact path is not a directory: {output_dir}")
        if any(output_dir.iterdir()):
            raise ReleaseError(f"Windows artifact directory is not empty: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(exist_ok=True)

    gui_name = f"EPG-Renderer_GUI_Windows_x64_v{version}.zip"
    with tempfile.TemporaryDirectory(
        prefix="epg-renderer-windows-stage-",
        dir=output_dir.parent,
    ) as directory:
        staging = Path(directory)
        staged_cli = staging / "epg-render.exe"
        staged_gui = staging / gui_name
        shutil.copyfile(cli, staged_cli)
        _write_gui_archive(gui, license_path, staged_gui, epoch=epoch)
        cli_target = Path(shutil.move(staged_cli, output_dir / staged_cli.name))
        gui_target = Path(shutil.move(staged_gui, output_dir / staged_gui.name))

    return WindowsBinaryArtifacts(
        version=version,
        cli_executable=cli_target,
        gui_archive=gui_target,
    )


def build_windows_binaries(
    root: Path,
    output_dir: Path,
    *,
    epoch: int = DEFAULT_SOURCE_DATE_EPOCH,
) -> WindowsBinaryArtifacts:
    """Build both PyInstaller specs and package the exact Windows deliverables."""

    if os.name != "nt":
        raise ReleaseError("Windows binaries must be built on a native Windows runner.")
    version = project_version(root)
    packaging = root / "packaging" / "windows"
    with tempfile.TemporaryDirectory(prefix="epg-renderer-windows-build-") as directory:
        workspace = Path(directory)
        dist = workspace / "dist"
        _run_pyinstaller(
            root,
            packaging / "epg-render.spec",
            dist,
            workspace / "work-cli",
            epoch=epoch,
        )
        _run_pyinstaller(
            root,
            packaging / "epg-render-gui.spec",
            dist,
            workspace / "work-gui",
            epoch=epoch,
        )
        return _package_artifacts(
            root,
            dist,
            output_dir,
            version=version,
            epoch=epoch,
        )


def main() -> int:
    """Build Windows artifacts and print their paths and SHA-256 digests."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("release/windows"))
    parser.add_argument("--source-date-epoch", type=int, default=DEFAULT_SOURCE_DATE_EPOCH)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        artifacts = build_windows_binaries(
            root,
            args.output_dir.resolve(),
            epoch=args.source_date_epoch,
        )
    except ReleaseError as exc:
        print(f"Windows binary build failed: {exc}", file=sys.stderr)
        return 1
    print(f"Version: {artifacts.version}")
    print(f"CLI executable: {artifacts.cli_executable}")
    print(f"CLI SHA-256: {sha256_file(artifacts.cli_executable)}")
    print(f"GUI archive: {artifacts.gui_archive}")
    print(f"GUI SHA-256: {sha256_file(artifacts.gui_archive)}")
    print("Windows binary build: yes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
