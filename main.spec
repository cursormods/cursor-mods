# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from pathlib import Path

# Build from Python/Windows dependencies, not unrelated tools injected into PATH.
# In particular, a newer app-local ucrtbase.dll can break Windows 10 startup.
system_root = Path(os.environ.get('SystemRoot', r'C:\Windows'))
os.environ['PATH'] = os.pathsep.join(str(p) for p in (
    Path(sys.executable).parent, Path(sys.base_prefix), Path(sys.base_prefix) / 'DLLs',
    system_root / 'System32', system_root,
))

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('assets', 'assets'), ('qml', 'qml'), ('mask.ico', '.'),
           ('LICENSE', '.'), ('THIRD_PARTY_NOTICES.md', '.'), ('licenses', 'licenses')],
    hiddenimports=['keyboard', 'win32com.client', 'pythoncom', 'PySide6.QtQuickControls2'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinterdnd2', 'pystray'],
    noarchive=False,
    optimize=0,
)
# Windows 10 supplies its own Universal CRT and API-set forwarding libraries.
a.binaries = [entry for entry in a.binaries
              if Path(entry[0]).name.lower() != 'ucrtbase.dll'
              and not Path(entry[0]).name.lower().startswith('api-ms-win-')]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='cursor-mods',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['mask.ico'],
)
