"""Bundle a released STRio version into EPG-Renderer, or verify the bundled copy.

EPG-Renderer reads GeneMapper exports with STRio (https://github.com/rsivth/strio). The
renderer has no runtime dependencies and must work from an unpacked source ZIP and as a
Windows program without network access, so it carries an exact copy of one STRio
release in ``src/epg_renderer/_vendor/strio``. ``src/epg_renderer/_vendor/VENDORED.json``
records the version and the SHA-256 of every copied file; the test suite rejects any
difference, so the copy is never edited by hand.

Usage, from the EPG-Renderer root, with a STRio checkout at the wanted release tag::

    python -m tools.vendor_strio ../strio            # replace the bundled copy
    python -m tools.vendor_strio ../strio --check    # compare checkout and bundled copy
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR_DIRECTORY = ROOT / "src" / "epg_renderer" / "_vendor"
PACKAGE_DIRECTORY = VENDOR_DIRECTORY / "strio"
MANIFEST = VENDOR_DIRECTORY / "VENDORED.json"
SOURCE_URL = "https://github.com/rsivth/strio"
_VERSION_RE = re.compile(r'^__version__ = "(\d+\.\d+\.\d+)"$', re.MULTILINE)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def package_files(package: Path) -> dict[str, Path]:
    """Return the distributable files of a STRio package directory by relative path."""

    files: dict[str, Path] = {}
    for path in sorted(package.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        if path.suffix in {".py", ".typed"}:
            files[path.relative_to(package).as_posix()] = path
    return files


def package_version(package: Path) -> str:
    """Return the version declared in ``version.py`` of a STRio package directory."""

    match = _VERSION_RE.search((package / "version.py").read_text(encoding="utf-8"))
    if match is None:
        raise ValueError(f"No X.Y.Z version found in {package / 'version.py'}.")
    return match.group(1)


def build_manifest(package: Path, license_file: Path) -> dict[str, object]:
    """Describe a package directory and its license file as a vendoring manifest."""

    files = {name: _sha256(path) for name, path in package_files(package).items()}
    files["LICENSE"] = _sha256(license_file)
    version = package_version(package)
    return {
        "name": "strio",
        "distribution": "strio-forensic",
        "version": version,
        "source": SOURCE_URL,
        "tag": f"v{version}",
        "license": "BSD-3-Clause",
        "files": dict(sorted(files.items())),
    }


def verify_vendored(vendor_directory: Path = VENDOR_DIRECTORY) -> list[str]:
    """Return every difference between the bundled copy and its manifest."""

    manifest_path = vendor_directory / "VENDORED.json"
    package = vendor_directory / "strio"
    if not manifest_path.is_file():
        return [f"Missing manifest {manifest_path.name}."]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    recorded: dict[str, str] = manifest["files"]
    present = dict(package_files(package))
    if (package / "LICENSE").is_file():
        present["LICENSE"] = package / "LICENSE"
    problems = [f"Missing bundled file {name}." for name in sorted(set(recorded) - set(present))]
    problems += [
        f"Unrecorded bundled file {name}." for name in sorted(set(present) - set(recorded))
    ]
    for name in sorted(set(recorded) & set(present)):
        if _sha256(present[name]) != recorded[name]:
            problems.append(f"Bundled file {name} differs from the recorded release.")
    if (package / "version.py").is_file() and package_version(package) != manifest["version"]:
        problems.append("Bundled version.py does not match the manifest version.")
    return problems


def vendor(checkout: Path) -> dict[str, object]:
    """Replace the bundled copy with ``checkout/src/strio`` and write the manifest."""

    package = checkout / "src" / "strio"
    license_file = checkout / "LICENSE"
    if not (package / "__init__.py").is_file() or not license_file.is_file():
        raise ValueError(f"{checkout} is not a STRio checkout (src/strio, LICENSE).")
    manifest = build_manifest(package, license_file)
    if PACKAGE_DIRECTORY.exists():
        shutil.rmtree(PACKAGE_DIRECTORY)
    for name, path in package_files(package).items():
        target = PACKAGE_DIRECTORY / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    shutil.copyfile(license_file, PACKAGE_DIRECTORY / "LICENSE")
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def compare(checkout: Path) -> list[str]:
    """Return the differences between a STRio checkout and the bundled copy."""

    package = checkout / "src" / "strio"
    expected = build_manifest(package, checkout / "LICENSE")
    recorded = json.loads(MANIFEST.read_text(encoding="utf-8"))
    problems = verify_vendored()
    if expected["version"] != recorded["version"]:
        problems.append(
            f"Checkout has STRio {expected['version']}, bundled is {recorded['version']}."
        )
    if expected["files"] != recorded["files"]:
        problems.append("Checkout files differ from the bundled copy.")
    return problems


def main(argv: list[str] | None = None) -> int:
    """Vendor or compare STRio and report the result."""

    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("checkout", type=Path, help="STRio checkout at the release tag")
    parser.add_argument("--check", action="store_true", help="compare only, change nothing")
    args = parser.parse_args(argv)
    if args.check:
        problems = compare(args.checkout)
        for problem in problems:
            print(problem, file=sys.stderr)
        print("Bundled STRio matches the checkout." if not problems else "Mismatch.")
        return 0 if not problems else 1
    manifest = vendor(args.checkout)
    print(f"Bundled STRio {manifest['version']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
