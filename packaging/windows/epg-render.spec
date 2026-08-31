# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

spec_directory = Path(SPECPATH)
project_root = spec_directory.parents[1]
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(spec_directory))

from spec_common import HIDDEN_IMPORTS, PACKAGE_DATA, windows_version_info


analysis = Analysis(
    [str(spec_directory / "cli_entry.py")],
    pathex=[str(project_root / "src")],
    binaries=[],
    datas=PACKAGE_DATA,
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
python_archive = PYZ(analysis.pure)

executable = EXE(
    python_archive,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="epg-render",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=windows_version_info(
        executable_name="epg-render.exe",
        description="EPG-Renderer command-line interface",
    ),
)
