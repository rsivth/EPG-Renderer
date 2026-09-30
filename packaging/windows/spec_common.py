"""Shared deterministic inputs for the EPG-Renderer Windows bundle specs."""

from __future__ import annotations

import os
import re
from pathlib import Path

from tools.release_tools import project_version

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_DATA = [
    (str(PROJECT_ROOT / "src" / "epg_renderer" / "data"), "epg_renderer/data"),
]
HIDDEN_IMPORTS = ["cairosvg", "PIL.Image"]


_WINDOWS_VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)(?:rc\d+|\.dev\d+)?")


def numeric_windows_version(version: str) -> tuple[int, int, int, int]:
    """Convert ``X.Y.Z``, ``X.Y.ZrcN`` or ``X.Y.Z.devN`` to a Windows file-version tuple.

    Windows file versions hold four numbers only, so a candidate or development suffix
    maps to ``X.Y.Z.0``; the complete version remains in the textual version fields.
    """

    match = _WINDOWS_VERSION.fullmatch(version)
    if match is None:
        raise ValueError(
            "Windows bundles require a version of the form X.Y.Z, X.Y.ZrcN or X.Y.Z.devN, "
            f"got {version!r}."
        )
    values = tuple(int(part) for part in match.groups())
    if any(value > 65535 for value in values):
        raise ValueError(f"Windows version components must not exceed 65535, got {version!r}.")
    return values[0], values[1], values[2], 0


def windows_version_info(*, executable_name: str, description: str) -> object | None:
    """Build native Windows version metadata, or return none on other platforms."""

    if os.name != "nt":
        return None

    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo,
        StringFileInfo,
        StringStruct,
        StringTable,
        VarFileInfo,
        VarStruct,
        VSVersionInfo,
    )

    version = project_version(PROJECT_ROOT)
    numeric_version = numeric_windows_version(version)
    return VSVersionInfo(
        ffi=FixedFileInfo(
            filevers=numeric_version,
            prodvers=numeric_version,
            mask=0x3F,
            flags=0x0,
            OS=0x40004,
            fileType=0x1,
            subtype=0x0,
            date=(0, 0),
        ),
        kids=[
            StringFileInfo(
                [
                    StringTable(
                        "040904B0",
                        [
                            StringStruct("CompanyName", "EPG-Renderer"),
                            StringStruct("FileDescription", description),
                            StringStruct("FileVersion", version),
                            StringStruct("InternalName", Path(executable_name).stem),
                            StringStruct("LegalCopyright", "Copyright (c) 2026 Roland Schultheiß"),
                            StringStruct("OriginalFilename", executable_name),
                            StringStruct("ProductName", "EPG-Renderer"),
                            StringStruct("ProductVersion", version),
                        ],
                    )
                ]
            ),
            VarFileInfo([VarStruct("Translation", [1033, 1200])]),
        ],
    )
