# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

spec_directory = Path(SPECPATH)
project_root = spec_directory.parents[1]
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(spec_directory))

from spec_common import HIDDEN_IMPORTS, PACKAGE_DATA, windows_version_info


analysis = Analysis(
    [str(spec_directory / "gui_entry.py")],
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
    [],
    exclude_binaries=True,
    name="EPG-Renderer-GUI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=windows_version_info(
        executable_name="EPG-Renderer-GUI.exe",
        description="EPG-Renderer graphical interface",
    ),
)

bundle = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="EPG-Renderer-GUI",
)
