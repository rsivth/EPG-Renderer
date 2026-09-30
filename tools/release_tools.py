"""Deterministic source-archive, distribution-build and release-verification helpers."""

from __future__ import annotations

import gzip
import hashlib
import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import venv
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from email import policy
from email.parser import Parser
from pathlib import Path, PurePosixPath

DEFAULT_SOURCE_DATE_EPOCH = 1784592000
_FORBIDDEN_DIRECTORY_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "release",
}
_FORBIDDEN_SUFFIXES = (".pyc", ".pyo")
_FORBIDDEN_FILE_NAMES = frozenset({".ds_store", "thumbs.db", "desktop.ini"})
_APPLE_DOUBLE_PREFIX = "._"
_ROOT_GENERATED_PATTERNS = (
    re.compile(r"^EPG-Renderer_v.+\.zip(?:\.sha256)?$"),
    re.compile(r"^epg_renderer-.+\.tar\.gz$"),
    re.compile(r"^epg_renderer-.+\.whl$"),
    re.compile(r"^(?:TEST|COVERAGE)_REPORT_.+\.txt$"),
)
_ALLOWED_ROOT_FILES = {
    ".gitattributes",
    ".gitignore",
    "CHANGELOG.md",
    "LICENSE",
    "README.md",
    "launch_gui.py",
    "pyproject.toml",
}
_ALLOWED_TOP_LEVEL_DIRECTORIES = {".github", "docs", "examples", "src", "tests"}
_ALLOWED_TOOL_FILES = {
    "__init__.py",
    "build_release.py",
    "build_windows_binaries.py",
    "coverage_policy.py",
    "github_release.py",
    "release_tools.py",
    "run_all_tests.py",
    "run_coverage_checks.py",
    "run_quality_checks.py",
    "run_release_checks.py",
}
_ALLOWED_PACKAGING_FILES = {
    "packaging/windows/cli_entry.py",
    "packaging/windows/epg-render-gui.spec",
    "packaging/windows/epg-render.spec",
    "packaging/windows/gui_entry.py",
    "packaging/windows/requirements.txt",
    "packaging/windows/spec_common.py",
}


class ReleaseError(RuntimeError):
    """Raised when a release artifact is incomplete, dirty or non-reproducible."""


@dataclass(frozen=True, slots=True)
class ReleaseArtifacts:
    """Paths and digests produced by a successful deterministic build."""

    version: str
    source_archive: Path
    source_sha256: Path
    sdist: Path
    wheel: Path
    source_digest: str
    sdist_digest: str
    wheel_digest: str


_EXPECTED_PROJECT_URLS = {
    "Homepage": "https://github.com/rsivth/EPG-Renderer",
    "Documentation": "https://github.com/rsivth/EPG-Renderer/blob/main/docs/index.md",
    "Repository": "https://github.com/rsivth/EPG-Renderer",
    "Issues": "https://github.com/rsivth/EPG-Renderer/issues",
    "Changelog": "https://github.com/rsivth/EPG-Renderer/blob/main/CHANGELOG.md",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    """Return the hexadecimal SHA-256 digest of one file."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def project_version(root: Path) -> str:
    """Return the synchronized project and package version."""

    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"\s*$', pyproject, re.MULTILINE)
    if match is None:
        raise ReleaseError("Could not determine project version from pyproject.toml.")
    version = match.group(1)
    version_source = (root / "src" / "epg_renderer" / "version.py").read_text(encoding="utf-8")
    if f'__version__ = "{version}"' not in version_source:
        raise ReleaseError("pyproject.toml and version.py contain different versions.")
    return version


def is_release_source(relative: Path) -> bool:
    """Return whether a relative path is explicitly allowed in a source release."""

    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        return False
    if any(
        part in _FORBIDDEN_DIRECTORY_NAMES or part.endswith(".egg-info") for part in relative.parts
    ):
        return False
    if relative.suffix.casefold() in _FORBIDDEN_SUFFIXES:
        return False
    if _is_operating_system_clutter(relative.name):
        return False
    if len(relative.parts) == 1:
        if relative.name in {".coverage", "coverage.json", "MANIFEST.sha256"}:
            return False
        if any(pattern.match(relative.name) for pattern in _ROOT_GENERATED_PATTERNS):
            return False
        return relative.name in _ALLOWED_ROOT_FILES
    if relative.parts[0] == "tools":
        return len(relative.parts) == 2 and relative.name in _ALLOWED_TOOL_FILES
    if relative.parts[0] == "packaging":
        return relative.as_posix() in _ALLOWED_PACKAGING_FILES
    return relative.parts[0] in _ALLOWED_TOP_LEVEL_DIRECTORIES


def _is_operating_system_clutter(name: str) -> bool:
    """Return whether a filename is desktop-environment clutter at any depth.

    These files are never part of a release and must be reported wherever they
    appear, not only in the project root.
    """

    return name.casefold() in _FORBIDDEN_FILE_NAMES or name.startswith(_APPLE_DOUBLE_PREFIX)


def _is_known_excluded(relative: Path) -> bool:
    if any(
        part in _FORBIDDEN_DIRECTORY_NAMES or part.endswith(".egg-info") for part in relative.parts
    ):
        return True
    if relative.suffix.casefold() in _FORBIDDEN_SUFFIXES:
        return True
    if len(relative.parts) == 1:
        if relative.name in {".coverage", "coverage.json", "MANIFEST.sha256"}:
            return True
        return any(pattern.match(relative.name) for pattern in _ROOT_GENERATED_PATTERNS)
    return False


def unexpected_release_paths(root: Path) -> tuple[Path, ...]:
    """Return files that are neither allowed sources nor recognized generated artifacts."""

    return tuple(
        path.relative_to(root)
        for path in sorted(root.rglob("*"), key=lambda item: item.as_posix().casefold())
        if path.is_file()
        and not is_release_source(path.relative_to(root))
        and not _is_known_excluded(path.relative_to(root))
    )


def source_files(root: Path) -> tuple[Path, ...]:
    """Return the complete explicitly allowed release-source inventory."""

    unexpected = unexpected_release_paths(root)
    if unexpected:
        raise ReleaseError(f"Unapproved files are present in the source tree: {unexpected}")
    files = tuple(
        path
        for path in sorted(root.rglob("*"), key=lambda item: item.as_posix().casefold())
        if path.is_file() and is_release_source(path.relative_to(root))
    )
    if not files:
        raise ReleaseError("No source files were selected for the release archive.")
    return files


def dirty_release_paths(root: Path) -> tuple[Path, ...]:
    """Return generated or forbidden files present in a release tree."""

    return tuple(
        path.relative_to(root)
        for path in sorted(root.rglob("*"), key=lambda item: item.as_posix().casefold())
        if path.is_file()
        and path.relative_to(root) != Path("MANIFEST.sha256")
        and not is_release_source(path.relative_to(root))
        and path.relative_to(root).parts[0] not in {".git"}
    )


def _manifest_text(root: Path, files: Iterable[Path]) -> str:
    lines = [f"{sha256_file(path)}  {path.relative_to(root).as_posix()}" for path in files]
    return "\n".join(lines) + "\n"


def _zip_info(name: str, epoch: int) -> zipfile.ZipInfo:
    timestamp = time.gmtime(max(epoch, 315532800))[:6]
    info = zipfile.ZipInfo(name, date_time=timestamp)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    info.flag_bits |= 0x800
    return info


def build_source_archive(root: Path, destination: Path, *, epoch: int) -> Path:
    """Build a byte-reproducible source ZIP with an internal SHA-256 manifest."""

    version = project_version(root)
    expected_name = f"EPG-Renderer_v{version}.zip"
    if destination.name != expected_name:
        raise ReleaseError(f"Source archive must be named {expected_name!r}.")
    files = source_files(root)
    prefix = f"EPG-Renderer_v{version}"
    manifest = _manifest_text(root, files).encode("utf-8")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        destination,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
        strict_timestamps=True,
    ) as archive:
        for path in files:
            relative = path.relative_to(root).as_posix()
            archive.writestr(_zip_info(f"{prefix}/{relative}", epoch), path.read_bytes())
        archive.writestr(_zip_info(f"{prefix}/MANIFEST.sha256", epoch), manifest)
    return destination


def verify_manifest(root: Path) -> None:
    """Verify that a source tree exactly matches its SHA-256 manifest."""

    manifest_path = root / "MANIFEST.sha256"
    if not manifest_path.is_file():
        raise ReleaseError("MANIFEST.sha256 is missing.")
    expected: dict[str, str] = {}
    for line_number, line in enumerate(manifest_path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            digest, relative = line.split("  ", 1)
        except ValueError as exc:
            raise ReleaseError(f"Invalid manifest line {line_number}.") from exc
        path = PurePosixPath(relative)
        if path.is_absolute() or ".." in path.parts or not relative:
            raise ReleaseError(f"Unsafe manifest path at line {line_number}: {relative!r}")
        if relative in expected:
            raise ReleaseError(f"Duplicate manifest entry: {relative}")
        expected[relative] = digest

    actual_files = {
        path.relative_to(root).as_posix(): path
        for path in root.rglob("*")
        if path.is_file() and path != manifest_path
    }
    if set(expected) != set(actual_files):
        missing = sorted(set(expected) - set(actual_files))
        unexpected = sorted(set(actual_files) - set(expected))
        raise ReleaseError(f"Manifest file set differs; missing={missing}, unexpected={unexpected}")
    for relative, expected_digest in expected.items():
        actual_digest = sha256_file(actual_files[relative])
        if actual_digest != expected_digest:
            raise ReleaseError(f"Manifest digest mismatch for {relative}.")


def verify_source_archive(archive_path: Path) -> Path:
    """Extract and validate one source archive; return the validated root path."""

    temporary = Path(tempfile.mkdtemp(prefix="epg-renderer-source-check-"))
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ReleaseError("Source archive contains duplicate members.")
        for name in names:
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts:
                raise ReleaseError(f"Unsafe source-archive member: {name!r}")
        archive.extractall(temporary)
    roots = [path for path in temporary.iterdir() if path.is_dir()]
    if len(roots) != 1:
        raise ReleaseError("Source archive must contain exactly one root directory.")
    root = roots[0]
    verify_manifest(root)
    forbidden = dirty_release_paths(root)
    if forbidden:
        raise ReleaseError(f"Forbidden generated paths in source archive: {forbidden}")
    return root


def _copy_source_tree(root: Path, destination: Path) -> None:
    for source in source_files(root):
        relative = source.relative_to(root)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def _build_wheel_once(root: Path, destination: Path, *, epoch: int) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    environment = {
        **os.environ,
        "SOURCE_DATE_EPOCH": str(epoch),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
    }
    result = subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(destination)],
        cwd=root,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ReleaseError(f"Wheel build failed:\n{result.stdout}\n{result.stderr}")
    wheels = tuple(destination.glob("*.whl"))
    if len(wheels) != 1:
        raise ReleaseError(f"Expected one wheel, found {len(wheels)}.")
    return wheels[0]


def _normalize_sdist(source: Path, destination: Path, *, epoch: int) -> None:
    """Repack a backend-produced sdist with deterministic tar and gzip metadata."""

    entries: list[tuple[tarfile.TarInfo, bytes | None]] = []
    with tarfile.open(source, mode="r:gz") as archive:
        members = archive.getmembers()
        names = [member.name for member in members]
        if len(names) != len(set(names)):
            raise ReleaseError("Source distribution contains duplicate members.")
        for member in members:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or not path.parts:
                raise ReleaseError(f"Unsafe source-distribution member: {member.name!r}")
            if not (member.isfile() or member.isdir()):
                raise ReleaseError(f"Unsupported source-distribution member type: {member.name!r}")
            payload: bytes | None = None
            if member.isfile():
                extracted = archive.extractfile(member)
                if extracted is None:
                    raise ReleaseError(
                        f"Could not read source-distribution member: {member.name!r}"
                    )
                payload = extracted.read()
            entries.append((member, payload))

    destination.parent.mkdir(parents=True, exist_ok=True)
    with (
        destination.open("wb") as raw_output,
        gzip.GzipFile(
            filename="",
            mode="wb",
            compresslevel=9,
            fileobj=raw_output,
            mtime=epoch,
        ) as compressed,
        tarfile.open(
            fileobj=compressed,
            mode="w",
            format=tarfile.PAX_FORMAT,
        ) as normalized,
    ):
        for original, payload in sorted(entries, key=lambda item: item[0].name):
            member = tarfile.TarInfo(original.name)
            member.uid = 0
            member.gid = 0
            member.uname = ""
            member.gname = ""
            member.mtime = epoch
            member.pax_headers = {}
            if original.isdir():
                member.type = tarfile.DIRTYPE
                member.mode = 0o755
                normalized.addfile(member)
            else:
                assert payload is not None
                member.type = tarfile.REGTYPE
                member.mode = 0o644
                member.size = len(payload)
                normalized.addfile(member, io.BytesIO(payload))


def _build_sdist_once(root: Path, destination: Path, *, epoch: int) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    raw_destination = destination / "backend-output"
    raw_destination.mkdir()
    environment = {
        **os.environ,
        "SOURCE_DATE_EPOCH": str(epoch),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
    }
    result = subprocess.run(
        [sys.executable, "-m", "build", "--sdist", "--outdir", str(raw_destination)],
        cwd=root,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ReleaseError(f"Source-distribution build failed:\n{result.stdout}\n{result.stderr}")
    raw_sdists = tuple(raw_destination.glob("*.tar.gz"))
    if len(raw_sdists) != 1:
        raise ReleaseError(f"Expected one source distribution, found {len(raw_sdists)}.")
    normalized = destination / raw_sdists[0].name
    _normalize_sdist(raw_sdists[0], normalized, epoch=epoch)
    shutil.rmtree(raw_destination)
    return normalized


def _validate_distribution_metadata(text: str, *, version: str) -> None:
    metadata = Parser(policy=policy.default).parsestr(text)
    expected_fields = {
        "Name": "epg-renderer",
        "Version": version,
        "Requires-Python": ">=3.10",
        "License-Expression": "BSD-3-Clause",
        "Description-Content-Type": "text/markdown",
        "Maintainer": "rsivth",
    }
    for field, expected in expected_fields.items():
        actual = metadata.get(field)
        if actual != expected:
            raise ReleaseError(
                f"Distribution metadata field {field!r} is {actual!r}, expected {expected!r}."
            )
    if "LICENSE" not in metadata.get_all("License-File", []):
        raise ReleaseError("Distribution metadata does not declare the bundled LICENSE file.")
    if "raster" not in metadata.get_all("Provides-Extra", []):
        raise ReleaseError("Distribution metadata does not declare the raster extra.")
    project_urls: dict[str, str] = {}
    for value in metadata.get_all("Project-URL", []):
        try:
            label, url = value.split(",", 1)
        except ValueError as exc:
            raise ReleaseError(f"Malformed Project-URL metadata: {value!r}") from exc
        project_urls[label.strip()] = url.strip()
    if project_urls != _EXPECTED_PROJECT_URLS:
        raise ReleaseError(
            f"Distribution project URLs differ; expected={_EXPECTED_PROJECT_URLS}, "
            f"actual={project_urls}."
        )


def inspect_wheel(wheel: Path, *, version: str) -> None:
    """Verify the file inventory and metadata of a built wheel."""

    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        metadata_names = [name for name in names if name.endswith(".dist-info/METADATA")]
        if len(metadata_names) != 1:
            raise ReleaseError(
                f"Wheel must contain one METADATA file, found {len(metadata_names)}."
            )
        metadata_name = metadata_names[0]
        metadata_text = archive.read(metadata_name).decode("utf-8")
        dist_info = metadata_name.removesuffix("METADATA")
        required_metadata = {
            f"{dist_info}entry_points.txt",
            f"{dist_info}licenses/LICENSE",
        }
        missing_metadata = sorted(required_metadata - set(names))
        if missing_metadata:
            raise ReleaseError(f"Wheel is missing distribution metadata: {missing_metadata}")
        entry_points = archive.read(f"{dist_info}entry_points.txt").decode("utf-8")
    if len(names) != len(set(names)):
        raise ReleaseError("Wheel contains duplicate members.")
    forbidden = [
        name
        for name in names
        if "__pycache__" in PurePosixPath(name).parts
        or name.endswith((".pyc", ".pyo"))
        or "/tests/" in f"/{name}"
    ]
    legacy_modules = {"epg_renderer/detection.py", "epg_renderer/renderer.py"}
    forbidden.extend(sorted(legacy_modules.intersection(names)))
    if forbidden:
        raise ReleaseError(f"Wheel contains forbidden files: {forbidden}")
    required = {
        "epg_renderer/version.py",
        "epg_renderer/data/kit_definition_schema.json",
    }
    missing = sorted(required - set(names))
    if missing:
        raise ReleaseError(f"Wheel is missing package resources: {missing}")
    if not metadata_name.endswith(f"epg_renderer-{version}.dist-info/METADATA"):
        raise ReleaseError("Wheel metadata does not match the release version.")
    _validate_distribution_metadata(metadata_text, version=version)
    for entry_point in (
        "epg-render = epg_renderer.cli:main",
        "epg-render-gui = epg_renderer.gui:main",
    ):
        if entry_point not in entry_points:
            raise ReleaseError(f"Wheel is missing console entry point: {entry_point!r}")
    kit_resources = [
        name
        for name in names
        if name.startswith("epg_renderer/data/kits/") and name.endswith(".json")
    ]
    if len(kit_resources) != 14:
        raise ReleaseError(f"Wheel must contain 14 kit profiles, found {len(kit_resources)}.")


def inspect_sdist(sdist: Path, *, version: str) -> None:
    """Verify the inventory and core metadata of a standard source distribution."""

    expected_name = f"epg_renderer-{version}.tar.gz"
    if sdist.name != expected_name:
        raise ReleaseError(f"Source distribution must be named {expected_name!r}.")
    expected_root = f"epg_renderer-{version}"
    with tarfile.open(sdist, mode="r:gz") as archive:
        members = archive.getmembers()
        names = [member.name.rstrip("/") for member in members]
        if len(names) != len(set(names)):
            raise ReleaseError("Source distribution contains duplicate members.")
        for member in members:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or not path.parts:
                raise ReleaseError(f"Unsafe source-distribution member: {member.name!r}")
            if path.parts[0] != expected_root:
                raise ReleaseError("Source distribution must contain exactly one versioned root.")
            if any(
                part in {".git", "__pycache__", "build", "dist", "release"} for part in path.parts
            ):
                raise ReleaseError(
                    f"Source distribution contains a forbidden path: {member.name!r}"
                )
            if member.name.endswith((".pyc", ".pyo")):
                raise ReleaseError(f"Source distribution contains compiled Python: {member.name!r}")
        required = {
            f"{expected_root}/LICENSE",
            f"{expected_root}/PKG-INFO",
            f"{expected_root}/README.md",
            f"{expected_root}/pyproject.toml",
            f"{expected_root}/src/epg_renderer/version.py",
            f"{expected_root}/src/epg_renderer/data/kit_definition_schema.json",
        }
        missing = sorted(required - set(names))
        if missing:
            raise ReleaseError(f"Source distribution is missing required files: {missing}")
        kit_resources = [
            name
            for name in names
            if name.startswith(f"{expected_root}/src/epg_renderer/data/kits/")
            and name.endswith(".json")
        ]
        if len(kit_resources) != 14:
            raise ReleaseError(
                f"Source distribution must contain 14 kit profiles, found {len(kit_resources)}."
            )
        pkg_info = archive.extractfile(f"{expected_root}/PKG-INFO")
        if pkg_info is None:
            raise ReleaseError("Could not read source-distribution PKG-INFO.")
        _validate_distribution_metadata(pkg_info.read().decode("utf-8"), version=version)


def check_distributions(*distributions: Path) -> None:
    """Require Twine to accept every distribution and its rendered long description."""

    if not distributions:
        raise ReleaseError("No Python distributions were supplied to Twine.")
    result = subprocess.run(
        [sys.executable, "-m", "twine", "check", "--strict", *map(str, distributions)],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ReleaseError(f"Twine distribution check failed:\n{result.stdout}\n{result.stderr}")


def _venv_python(directory: Path) -> Path:
    return directory / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def test_extracted_source(root: Path) -> None:
    """Run a focused import and render smoke test from an extracted source archive."""

    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run(
        [sys.executable, "tests/smoke/source_smoke_test.py"],
        cwd=root,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ReleaseError(
            f"Extracted source archive smoke test failed:\n{result.stdout}\n{result.stderr}"
        )


def _create_clean_environment(workspace: Path, name: str) -> tuple[Path, Path]:
    environment_dir = workspace / name
    venv.EnvBuilder(
        with_pip=True,
        clear=True,
        symlinks=os.name != "nt",
    ).create(environment_dir)
    return environment_dir, _venv_python(environment_dir)


def _install_wheel(python: Path, wheel: Path, *, raster: bool) -> None:
    requirement = f"{wheel}[raster]" if raster else str(wheel)
    arguments = [str(python), "-m", "pip", "install"]
    if not raster:
        arguments.append("--no-deps")
    arguments.append(requirement)
    result = subprocess.run(arguments, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        mode = "raster" if raster else "minimal"
        raise ReleaseError(
            f"{mode.capitalize()} wheel installation failed:\n{result.stdout}\n{result.stderr}"
        )


def _install_sdist(python: Path, sdist: Path) -> None:
    result = subprocess.run(
        [str(python), "-m", "pip", "install", "--no-deps", str(sdist)],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ReleaseError(
            f"Source-distribution installation failed:\n{result.stdout}\n{result.stderr}"
        )


def _run_source_tests(python: Path, root: Path, *, label: str) -> None:
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run(
        [str(python), "-m", "tools.run_all_tests"],
        cwd=root,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ReleaseError(f"{label} test suite failed:\n{result.stdout}\n{result.stderr}")


def _verify_installed_svg(python: Path, workspace: Path, *, version: str) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    fixture = workspace / "smoke.tsv"
    fixture.write_text(
        "Sample Name\tMarker\tDye\tAllele 1\tHeight 1\nSmoke\tD3S1358\tB\t15\t500\n",
        encoding="utf-8",
    )
    output = workspace / "smoke.svg"
    command = subprocess.run(
        [
            str(python),
            "-m",
            "epg_renderer",
            str(fixture),
            str(output),
            "--kit",
            "GlobalFiler",
        ],
        cwd=workspace,
        text=True,
        capture_output=True,
        check=False,
    )
    if command.returncode != 0:
        raise ReleaseError(f"Installed CLI smoke test failed:\n{command.stdout}\n{command.stderr}")
    svg = output.read_text(encoding="utf-8")
    if f'data-epg-renderer-version="{version}"' not in svg or 'data-kit="GlobalFiler"' not in svg:
        raise ReleaseError("Installed wheel generated invalid release metadata.")


def test_minimal_installation(
    wheel: Path, workspace: Path, source_root: Path, *, version: str
) -> None:
    """Verify the wheel and complete tests without optional raster dependencies."""

    environment_dir, python = _create_clean_environment(workspace, "minimal-venv")
    _install_wheel(python, wheel, raster=False)
    absence = subprocess.run(
        [
            str(python),
            "-c",
            (
                "import importlib.util; "
                "assert importlib.util.find_spec('PIL') is None; "
                "assert importlib.util.find_spec('cairosvg') is None"
            ),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if absence.returncode != 0:
        raise ReleaseError(
            "Minimal environment unexpectedly contains raster dependencies:\n"
            f"{absence.stdout}\n{absence.stderr}"
        )
    _verify_installed_svg(python, workspace / "minimal-smoke", version=version)
    _run_source_tests(python, source_root, label="Minimal-dependency")
    dependency_check = subprocess.run(
        [str(python), "-m", "pip", "check"],
        cwd=environment_dir,
        text=True,
        capture_output=True,
        check=False,
    )
    if dependency_check.returncode != 0:
        raise ReleaseError(
            f"Minimal pip check failed:\n{dependency_check.stdout}\n{dependency_check.stderr}"
        )


def test_raster_installation(
    wheel: Path, workspace: Path, source_root: Path, *, version: str
) -> None:
    """Verify the optional raster extra and its CLI/integration tests."""

    _, python = _create_clean_environment(workspace, "raster-venv")
    _install_wheel(python, wheel, raster=True)
    probe = subprocess.run(
        [
            str(python),
            "-c",
            (
                "import cairosvg; from PIL import Image; import epg_renderer as e; "
                f"assert e.__version__ == {version!r}; assert len(e.list_kits()) == 14"
            ),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if probe.returncode != 0:
        raise ReleaseError(f"Raster dependency probe failed:\n{probe.stdout}\n{probe.stderr}")
    _run_source_tests(python, source_root, label="Raster-enabled")
    dependency_check = subprocess.run(
        [str(python), "-m", "pip", "check"],
        text=True,
        capture_output=True,
        check=False,
    )
    if dependency_check.returncode != 0:
        raise ReleaseError(
            f"Raster pip check failed:\n{dependency_check.stdout}\n{dependency_check.stderr}"
        )


def test_sdist_installation(sdist: Path, workspace: Path, *, version: str) -> None:
    """Build and install the sdist through pip, then exercise the installed CLI."""

    environment_dir, python = _create_clean_environment(workspace, "sdist-venv")
    _install_sdist(python, sdist)
    probe = subprocess.run(
        [
            str(python),
            "-c",
            (
                "import epg_renderer as e; "
                f"assert e.__version__ == {version!r}; assert len(e.list_kits()) == 14"
            ),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if probe.returncode != 0:
        raise ReleaseError(
            f"Source-distribution import probe failed:\n{probe.stdout}\n{probe.stderr}"
        )
    _verify_installed_svg(python, workspace / "sdist-smoke", version=version)
    dependency_check = subprocess.run(
        [str(python), "-m", "pip", "check"],
        cwd=environment_dir,
        text=True,
        capture_output=True,
        check=False,
    )
    if dependency_check.returncode != 0:
        raise ReleaseError(
            f"Source-distribution pip check failed:\n"
            f"{dependency_check.stdout}\n{dependency_check.stderr}"
        )


def smoke_test_wheel(wheel: Path, workspace: Path, source_root: Path, *, version: str) -> None:
    """Verify minimal and raster-enabled wheel installations independently."""

    test_minimal_installation(wheel, workspace, source_root, version=version)
    test_raster_installation(wheel, workspace, source_root, version=version)


def build_reproducible_release(
    root: Path,
    output_dir: Path,
    *,
    epoch: int = DEFAULT_SOURCE_DATE_EPOCH,
    smoke_test: bool = True,
    source_test: bool = True,
) -> ReleaseArtifacts:
    """Build source ZIP, sdist, and wheel twice and publish one verified set."""

    version = project_version(root)
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="epg-renderer-release-") as directory:
        temporary = Path(directory)
        source_archives: list[Path] = []
        sdists: list[Path] = []
        wheels: list[Path] = []
        for index in (1, 2):
            stage_root = temporary / f"stage-{index}"
            source_stage = stage_root / "source"
            sdist_stage = stage_root / "sdist"
            wheel_stage = stage_root / "wheel"
            for staged in (source_stage, sdist_stage, wheel_stage):
                _copy_source_tree(root, staged)
            source_archive = temporary / f"source-{index}" / f"EPG-Renderer_v{version}.zip"
            source_archive.parent.mkdir(parents=True)
            build_source_archive(source_stage, source_archive, epoch=epoch)
            source_archives.append(source_archive)
            sdists.append(_build_sdist_once(sdist_stage, temporary / f"sdist-{index}", epoch=epoch))
            wheels.append(_build_wheel_once(wheel_stage, temporary / f"wheel-{index}", epoch=epoch))

        if source_archives[0].read_bytes() != source_archives[1].read_bytes():
            raise ReleaseError("Two clean source-archive builds are not byte-reproducible.")
        if sdists[0].read_bytes() != sdists[1].read_bytes():
            raise ReleaseError("Two clean source-distribution builds are not byte-reproducible.")
        if wheels[0].read_bytes() != wheels[1].read_bytes():
            raise ReleaseError("Two clean wheel builds are not byte-reproducible.")

        source_target = output_dir / source_archives[0].name
        sdist_target = output_dir / sdists[0].name
        wheel_target = output_dir / wheels[0].name
        shutil.copyfile(source_archives[0], source_target)
        shutil.copyfile(sdists[0], sdist_target)
        shutil.copyfile(wheels[0], wheel_target)
        inspect_sdist(sdist_target, version=version)
        inspect_wheel(wheel_target, version=version)
        check_distributions(sdist_target, wheel_target)
        extracted = verify_source_archive(source_target)
        try:
            if source_test:
                test_extracted_source(extracted)
        finally:
            shutil.rmtree(extracted.parent)
        if smoke_test:
            smoke_test_wheel(
                wheel_target,
                temporary / "smoke",
                temporary / "stage-1" / "source",
                version=version,
            )
            test_sdist_installation(sdist_target, temporary / "smoke", version=version)

    source_digest = sha256_file(source_target)
    sdist_digest = sha256_file(sdist_target)
    wheel_digest = sha256_file(wheel_target)
    sha_target = output_dir / f"{source_target.name}.sha256"
    sha_target.write_text(f"{source_digest}  {source_target.name}\n", encoding="utf-8")
    return ReleaseArtifacts(
        version=version,
        source_archive=source_target,
        source_sha256=sha_target,
        sdist=sdist_target,
        wheel=wheel_target,
        source_digest=source_digest,
        sdist_digest=sdist_digest,
        wheel_digest=wheel_digest,
    )


__all__ = [
    "DEFAULT_SOURCE_DATE_EPOCH",
    "ReleaseArtifacts",
    "ReleaseError",
    "build_reproducible_release",
    "build_source_archive",
    "check_distributions",
    "dirty_release_paths",
    "inspect_sdist",
    "inspect_wheel",
    "is_release_source",
    "project_version",
    "sha256_file",
    "smoke_test_wheel",
    "source_files",
    "test_extracted_source",
    "test_minimal_installation",
    "test_raster_installation",
    "test_sdist_installation",
    "unexpected_release_paths",
    "verify_manifest",
    "verify_source_archive",
]
